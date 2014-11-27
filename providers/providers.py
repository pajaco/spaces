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


class EnvProvider(object):
    """Provides setting and exporting environment variables"""
    def __init__(self, space, **kwargs):
        self.space = space
        self._env_vars = kwargs
        self.bac_preamble = "_SPACES_%s_" % self.space

    def provide(self):
        # check if variable set, back up if yes, export new one
        keys = self._env_vars.keys()
        # ensure variables having other baked in go to the end of queue
        keys.sort(cmp=lambda x, y: -1 if x in self._env_vars[y] else 0)
        out = []
        for k, v in self._env_vars.items():
            test = "test -z \"$%s\"" % k
            positive = "export {0}={1}".format(k, v)
            negative = "".join([self.bac_preamble,
                               "{0}=${0} && {1}".format(k, positive)])
            out.append((test, positive, negative))
        return out

    def revert(self):
        out = []
        for k in self._env_vars.keys():
            test = "env | grep %s%s" % (self.bac_preamble, k)
            positive = "export {0}=${1}{0}; unset {1}{0}".format(
                k, self.bac_preamble)
            negative = "unset {0}{1}".format(self.bac_preamble, k)
            out.append((test, positive, negative))
        return out


class VirtualenvProvider(object):
    def __init__(self, space, **kwargs):
        self.space = space
        self.path = kwargs['path']

    def check_dependency(self):
        return "which virtualenv"

    def provide(self):
        test = 'test -d %s -a -f %s/bin/activate' % (self.path, self.path)
        positive = 'source %s/bin/activate' % self.path
        negative = ' && '.join(['virtualenv %s' % self.path,
                                positive])
        return test, positive, negative

    def revert(self):
        test = 'env | grep VIRTUAL_ENV=%s' % self.path
        positive = 'deactivate'
        return test, positive, None


class PkgProvider(object):
    """Base class for package handling"""
    def __init__(self, space, **kwargs):
        self.space = space
        self.name = kwargs['name']
        self.version = kwargs['version']

    def revert(self):
        return None

    concrete_implementations = set()

    @classmethod
    def factory(cls, **kwargs):
        candidates = [provider for provider in cls.concrete_implementations
                      if provider.compatible_platform()]
        if len(candidates) < 1:
            raise RuntimeError("No concrete implementation available")
        if len(candidates) > 1:
            raise RuntimeError(
                "More than one concrete implementation available")
        return candidates[0](**kwargs)


class PipProvider(PkgProvider):
    """Provides python packages' installations via pip"""
    # TODO handle upgrade/downgrade
    def provide(self):
        if self.version:
            test = 'pip freeze | grep %s==%s' % (self.name, self.version)
            install = 'pip install %s==%s' % (self.name, self.version)
        else:
            test = 'pip freeze | grep %s' % (self.name)
            install = 'pip install %s' % (self.name)
        return test, None, install


class DebPkgProvider(PkgProvider):
    """Provides deb packages' installations"""
    def provide(self):
        if self.version:
            test = ('dpkg-query -W --showformat=\'${Status}*${Version}\' %s '
                    '| grep "install ok installed*%s"') % (
                        self.name, self.version)
            install = 'sudo apt-get install %s==%s' % (self.name, self.version)
        else:
            test = ('dpkg-query -W --showformat=\'${Status}\' %s '
                    '| grep "install ok installed"') % (self.name, self.version)
            install = 'sudo apt-get install %s' % (self.name, self.version)
        return test, None, install

    @staticmethod
    def compatible_platform():
        return platform.dist()[0].lower() == 'debian'

PkgProvider.concrete_implementations.add(DebPkgProvider)


class RpmPkgProvider(PkgProvider):
    """Provides rpm packages' installations"""
    def provide(self):
        if self.version:
            test = 'rpm -q {0} | grep {0}-{1}'.format(self.name, self.version)
            install = 'yum install -y {0}-{1}'.format(self.name, self.version)
        else:
            test = 'rpm -q %s' % self.name
            install = 'yum install -y %s' % self.name
        return test, None, install

    @staticmethod
    def compatible_platform():
        return platform.dist()[0].lower() == 'redhat'


class GitProvider(object):
    def __init__(self, space, **kwargs):
        self.path = kwargs['path']
        self.origin = kwargs['origin']
        self.ignore = [] # private ignore, doesn't go to .gitignore
        for ignore in kwargs.get('ignore', []):
            if ignore.startswith(self.path):
                self.ignore.append(ignore[len(self.path):])
            else:
                self.ignore.append(ignore)

    def provide(self):
        out = []
        # no repo, no dir
        test = "test ! -d {0}".format(self.path)
        positive = "git clone {0} {1}".format(self.origin, self.path)
        out.append((test, positive, None))
        # dir but no repo
        # TODO should it be created at this point???
        test = ("popd {0} && rc=$(git rev-parse --is-inside-work-tree) "
                "&& popd; test $rc").format(self.path)

        negative = ["pushd {0}",
                    "git init",
                    "git remote add origin {1}",
                    "git checkout -t origin/master",
                    "popd"]
        negative = " && ".join(negative).format(self.path, self.origin)
        out.append((test, None, negative))
        # ignore
        exclude_path = os.path.join(self.path, ".git/info/exclude")
        for ignore in self.ignore:
            test = "grep '%s' %s" % (ignore, exclude_path)
            negative = "cat >>{0} <<EOF{1}\nEOF".format(exclude_path, ignore)
            out.append((test, None, negative))
        return out


if __name__ == "__main__":
    import ipdb;
    # TODO integration tests make more sense but for now...
    env_provider = EnvProvider('testspace', A='$TMP/blah', TMP='/tmp')
    provided = env_provider.provide()
    expected = [
            ('test -z "$TMP"', 'export TMP=/tmp',
                '_SPACES_testspace_TMP=$TMP && export TMP=/tmp'),
            ('test -z "$A"', 'export A=$TMP/blah',
                '_SPACES_testspace_A=$A && export A=$TMP/blah')
            ]
    assert expected == provided
    reverted = env_provider.revert()
    expected = [
            ('env | grep _SPACES_testspace_TMP',
             ('export TMP=$_SPACES_testspace_TMP; '
              'unset _SPACES_testspace_TMP'),
             'unset _SPACES_testspace_TMP'),
            ('env | grep _SPACES_testspace_A',
             ('export A=$_SPACES_testspace_A; '
              'unset _SPACES_testspace_A'),
             'unset _SPACES_testspace_A'),
            ]
    assert expected == reverted

    venv_provider = VirtualenvProvider('testspace', path='~/env')
    assert 'which virtualenv' == venv_provider.check_dependency()
    provided = venv_provider.provide()
    expected = ('test -d ~/env -a -f ~/env/bin/activate',
                'source ~/env/bin/activate',
                ('virtualenv ~/env && '
                 'source ~/env/bin/activate'))
    assert expected == provided
    reverted = venv_provider.revert()
    expected = ('env | grep VIRTUAL_ENV=~/env',
                'deactivate',
                None)
    assert expected == reverted

    git_provider = GitProvider('testspace',
                               origin='git@github.com/pajaco/spaces',
                               path='~/spaces',
                               ignore=['*.swp'])
    result = git_provider.provide()
    expected = [('test ! -d ~/spaces',
                 'git clone git@github.com/pajaco/spaces ~/spaces',
                 None),
                (("popd ~/spaces && "
                  "rc=$(git rev-parse --is-inside-work-tree) && "
                  "popd; test $rc"),
                 None,
                 ('pushd ~/spaces && git init && '
                  'git remote add origin git@github.com/pajaco/spaces && '
                  'git checkout -t origin/master && popd')),
                ("grep '*.swp' ~/spaces/.git/info/exclude",
                 None,
                 'cat >>~/spaces/.git/info/exclude <<EOF*.swp\nEOF')]
    assert expected == result
