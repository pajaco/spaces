"""
Providers of scripts for spaces setup

Method 1: provide() -> test, positive case, negative case
Method 2 (optional): revert()
Method 3 (optional): check_dependency()

The directing component will use those when 'spaces enter <space>' is issued
and will run the check (1) then depending on the result (2) or not.

If appling state results in error then leaving state check (3) is called and
depending on the checks result (4) may be called to clean up

Providers shouldn't rely on doing own tests of state as their output once
generated needs to be self-sufficient.
"""

import os
import platform
import ipdb


class StopTheLine(Exception):
    """Named in honour of Nick Forbes, the best manager ever"""
    pass


class EnvProvider(object):
    """Provide setting and exporting environment variables"""

    append_only = []

    def __init__(self, params):
        self._env_vars = params.copy()
        self._backup = {}

    def _save_current_vars(self, stdout):
        lines = stdout.split("\n")
        for line in lines:
            name, value = line.split("=", 1)
            if name in self._env_vars:
                self._backup[name] = value

    def _get_export_commands(self):
        names = self._env_vars.keys()
        # ensure variables having other baked in go to the end of queue
        names.sort(cmp=lambda x, y: -1 if x in self._env_vars[y] else 0)
        return ["export %s=%s" % (name, self._env_vars[name])
                for name in names]

    def provide(self):
        """Set environment variables (back up existing)"""
        _, stdout, _ = yield "env"
        self._save_current_vars(stdout)
        for cmd in self._get_export_commands():
            yield cmd

    def revert(self):
        """Restore environment variables"""
        for var, val in self._backup.iteritems():
            yield "export %s=%s" % (var, val)
        if self._backup:
            backup_keys = self._backup.keys()
            yield "unset %s" % " ".join([var for var in self._env_vars.keys()
                                         if var not in backup_keys])
        else:
            yield "unset %s" % " ".join(self._env_vars.keys())


class VirtualenvProvider(object):
    """Provide virtualenv"""
    def __init__(self, params):
        self.path = params['path']

    def provide(self):
        """Set up and activate virtualenv"""
        rcode, stdout, _ = yield "which virtualenv"
        if rcode != 0:
            raise StopTheLine("Virtualenv is not installed")
        virtualenv = stdout
        activate_path = '%s/bin/activate' % self.path
        rcode, _, _ = yield "test -f %s" % activate_path
        if rcode != 0:
            rcode, _, _ = yield "%s %s" % (virtualenv, self.path)
            if rcode != 0:
                raise StopTheLine("Virtualenv setup failed")
        # we have env set up
        rcode, _, _ = yield 'test -z "$VIRTUAL_ENV"'
        if rcode != 0:
            yield "source %s" % activate_path

    def revert(self):
        """Deactivate virtualenv"""
        rcode, stdout, _ = yield "type -t deactivate"
        if rcode == 0 and stdout.strip() == 'function':
            yield 'deactivate'  # bash function


class PkgProvider(object):
    """Base class for package handling"""
    def __init__(self, params):
        self._packages = params
        self._backup = {}

    def _get_upgrades_and_installs(self, installed, ver_mark):
        to_install = []
        to_upgrade = []
        for package, version in self._packages.iteritems():
            if package in installed:
                if not version:
                    to_upgrade.append(package)
                elif installed[package] != version:
                    to_upgrade.append("%s%s%s" % (package, ver_mark, version))
            elif not version:
                to_install.append(package)
            else:
                to_install.append("%s%s%s" % (package, ver_mark, version))
        return to_install, to_upgrade

    concrete_implementations = set()

    def __new__(cls, params):
        if cls is PkgProvider:
            candidates = [provider for provider in cls.concrete_implementations
                          if provider.compatible_platform()]
            if len(candidates) < 1:
                raise RuntimeError("No concrete implementation available")
            if len(candidates) > 1:
                raise RuntimeError(
                    "More than one concrete implementation available")
            return super(PkgProvider, cls).__new__(
                    candidates[0], params)
        else:
            return super(PkgProvider, cls).__new__(cls, params)


class PipProvider(PkgProvider):
    """Provides python packages installed with pip"""
    def provide(self):
        rcode, stdout, _ = yield "which pip"
        if rcode != 0:
            raise StopTheLine("Pip is not installed")
        pip = stdout
        installed = {}
        _, stdout, _ = yield "%s freeze" % pip
        for line in stdout.split("\n"):
            name, version = line.split("==")
            installed[name] = version

        to_install, to_upgrade = self._get_upgrades_and_installs(
                installed, '==')
        rcode, _, _ = yield " ".join(["%s install -U" % pip] + to_upgrade)
        if rcode == 0:
            rcode, _, _ = yield " ".join(
                    ["%s install" % pip] + to_install)
            if rcode != 0:
                raise StopTheLine("Installing packages failed")
        else:
            raise StopTheLine("Upgrading packages failed")


class DebPkgProvider(PkgProvider):
    """Provides deb packages' installations"""
    def provide(self):
        rcode, apt, _ = yield "which apt-get"
        if rcode != 0:
            raise StopTheLine("apt-get not available")
        rcode, dpkg_query, _ = yield "which dpkg-query"
        if rcode != 0:
            raise StopTheLine("dpkg-query not available")
        cmd = "%s -W --showformat='${Package}==${Version}\n'" % dpkg_query
        _, stdout, _ = yield cmd

        installed = {}
        for line in stdout.strip().split("\n"):
            name, version = line.split("==")
            installed[name] = version
        to_install, to_upgrade = self._get_upgrades_and_installs(
                installed, '=')

        rcode, _, _ = yield "sudo %s update" % apt
        if rcode != 0:
            raise StopTheLine("Failed to update apt-get cache")
        if to_upgrade:
            rcode, _, _ = yield " ".join(
                ["sudo %s upgrade" % apt] + to_upgrade)
        if rcode != 0:
            raise StopTheLine("Debian packages installation failed")
        if to_install:
            rcode, _, _ = yield " ".join(
                    ["sudo %s install" % apt] + to_install)

    @staticmethod
    def compatible_platform():
        return platform.dist()[0].lower() == 'debian'

PkgProvider.concrete_implementations.add(DebPkgProvider)


class RpmPkgProvider(PkgProvider):
    """Provides rpm packages' installations"""

    def provide(self):
        """Install and upgrade rpm packages"""
        rcode, rpm, _ = yield "which rpm"
        if rcode != 0:
            raise StopTheLine("rpm not available")
        rcode, yum, _ = yield "which yum"
        if rcode != 0:
            raise StopTheLine("yum not available")
        _, stdout, _ = yield "%s -qa" % rpm
        installed = {}
        for line in stdout.strip().split("\n"):
            name, version = line.split("-")
            installed[name] = version
        to_install, to_upgrade = self._get_upgrades_and_installs(
                installed, '-')
        rcode, _, _ = yield "sudo %s makecache" % yum
        if rcode != 0:
            raise StopTheLine("Failed to update yum cache")
        if to_upgrade:
            rcode, _, _ = yield " ".join(
                ["sudo %s upgrade -y" % yum] + to_upgrade)
        if rcode != 0:
            raise StopTheLine("RPM packages' installation failed")
        if to_install:
            rcode, _, _ = yield " ".join(
                    ["sudo %s install -y" % yum] + to_install)

    @staticmethod
    def compatible_platform():
        return platform.dist()[0].lower() == 'redhat'


class GitProvider(object):
    def __init__(self, params):
        self.path = params['path']
        self.origin = params['origin']
        self.ignore = []  # private ignore, goes to .git/info/exclude
        for ignore in params.get('ignore', []):
            if ignore.startswith(self.path):
                self.ignore.append(ignore[len(self.path):])
            else:
                self.ignore.append(ignore)

    def provide(self):
        rcode, git, _ = yield "which git"
        if rcode != 0:
            raise StopTheLine("Git is not installed")

        rcode, _, _ = yield "test -d %s" % self.path
        if rcode == 0:
            raise StopTheLine("Directory already exists")
        rcode, _, _ = yield "%s clone %s %s" % (git, self.origin, self.path)
        if rcode != 0:
            raise StopTheLine("Cannot clone repo")
        # ignore
        exclude_path = os.path.join(self.path, ".git/info/exclude")
        ignore = "\n".join(self.ignore)
        _, _, _ = yield "cat >>%s <<EOF%s\nEOF" % (exclude_path, ignore)


if __name__ == "__main__":
    env_provider = EnvProvider(params=dict(A='$TMP/blah', TMP='/tmp'))
    result = env_provider.provide()
    assert "env" == result.next()
    stdout = "SHELL=/bin/bash\nUSER=jks\nTMP=/another"
    assert "export TMP=/tmp" == result.send((0, stdout, ""))
    assert "export A=$TMP/blah" == result.send((0, "", ""))
    try:
        result.send((0, "", ""))
    except StopIteration as e:
        assert True
    result = env_provider.revert()
    assert "export TMP=/another" == result.next()
    assert "unset A" == result.next()

    venv_provider = VirtualenvProvider(params=dict(path='~/env'))
    result = venv_provider.provide()
    assert "which virtualenv" == result.next()
    assert "test -f ~/env/bin/activate" == result.send(
            (0, "/usr/local/bin/virtualenv", ""))
    assert "/usr/local/bin/virtualenv ~/env" == result.send((1, "", ""))
    assert "test -z \"$VIRTUAL_ENV\"" == result.send((0, "", ""))
    assert "source ~/env/bin/activate" == result.send((1, "", ""))
    try:
        result.send((0, "", ""))
    except StopIteration as e:
        pass
    result = venv_provider.revert()
    assert "type -t deactivate" == result.next()
    assert "deactivate" == result.send((0, "function\n", ""))

    pip_provider = PipProvider(params={'ipython': '1.2.0',
                                       'nosuchone': None})
    result = pip_provider.provide()
    assert "which pip" == result.next()
    assert "/usr/bin/pip freeze" == result.send((0, "/usr/bin/pip", ""))
    cmd = result.send((0, "ipython==1.1.0", ""))
    assert "/usr/bin/pip install -U ipython==1.2.0" == cmd
    cmd = result.send((0, "", ""))
    assert "/usr/bin/pip install nosuchone" == cmd

    deb_provider = DebPkgProvider(params=dict(finger=None, wget='1.13.4'))
    result = deb_provider.provide()
    assert "which apt-get" == result.next()
    assert "which dpkg-query" == result.send((0, '/usr/bin/apt-get', ''))
    out = "/usr/bin/dpkg-query -W --showformat='${Package}==${Version}\n'"
    assert out == result.send((0, '/usr/bin/dpkg-query', ''))
    assert "sudo /usr/bin/apt-get update" == result.send(
            (0, "foo==1.1.1\nwget==1.0.1", ""))
    cmd = result.send((0, "", ""))
    assert "sudo /usr/bin/apt-get upgrade wget=1.13.4" == cmd
    cmd = result.send((0, "", ""))
    assert "sudo /usr/bin/apt-get install finger" == cmd

    rpm_provider = RpmPkgProvider(params=dict(finger=None, wget='1.13.4'))
    result = rpm_provider.provide()
    assert "which rpm" == result.next()
    assert "which yum" == result.send((0, '/usr/bin/rpm', ''))
    cmd = result.send((0, '/usr/bin/yum', ''))
    assert "/usr/bin/rpm -qa" == cmd
    assert "sudo /usr/bin/yum makecache" == result.send(
            (0, "foo-1.1.1\nwget-1.0.1", ""))
    cmd = result.send((0, "", ""))
    assert "sudo /usr/bin/yum upgrade -y wget-1.13.4" == cmd
    cmd = result.send((0, "", ""))
    assert "sudo /usr/bin/yum install -y finger" == cmd

    git_provider = GitProvider(
        params=dict(origin='git@github.com/pajaco/spaces',
                    path='~/spaces', ignore=['*.swp']))
    result = git_provider.provide()
    assert "which git" == result.next()
    assert "test -d ~/spaces" == result.send((0, '/usr/bin/git', ''))
    cmd = result.send((1, "", ""))
    assert "/usr/bin/git clone git@github.com/pajaco/spaces ~/spaces" == cmd
    cmd = result.send((0, "", ""))
    assert "cat >>~/spaces/.git/info/exclude <<EOF*.swp\nEOF" == cmd
