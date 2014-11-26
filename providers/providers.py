"""
Providers of scripts for spaces setup

Method 1: provide() -> test, positive case, negative case
Method 2 (optional): revert()
Method 3 (optional): check_dependency()

The directing component will use those when 'spaces enter <space>' is issued
and will run the check (1) then depending on the result (2) or not.

If appling state results in error then leaving state check (3) is called and
depending on the checks result (4) may be called to clean up

Each provider stores the state it found initially for the revert action.

Providers shouldn't rely on doing own tests of state as their output once
generated needs to be self-sufficient.
"""
from distutils.spawn import find_executable


class EnvProvider(object):
    """Provides setting and exporting environment variables"""
    def __init__(self, space, **kwargs):
        self.space = space
        # TODO order them so that env vars containing other will be processed
        # later
        self._env_vars = kwargs
        self.bac_preamble = "_SPACES_{0}_" % self.space

    def provide(self):
        # check if variable set, back up if yes, export new one
        out = []
        for k, v in self._env_vars.items():
            test = "test -z \"$%s\""
            positive = "export {0}={1}".format(k, v)
            negative = "".join(self.bac_preamble,
                               "{0}={1} && {2}".format(k, v, positive))
            out.append((test, positive, negative))
        return out
        
    def revert(self):
        out = []
        for k in self._env_vars.keys():
            test = "env | grep %s%s" % (self.bac_preamble, k)
            positive = "export {0}=${1}{0}; unset {1}{0}".format(
                    k, self.bac_preamble)
            negative = "unset {0}{1}".format(self.bac_preamble, k)
            out.append(test, positive, negative)
        return out

class VirtualenvProvider(object):
    def __init__(self, **kwargs):
        self.path = kwargs['path']

    def check_dependency(self):
        return "which virtualenv"

    def provide(self):
        test = "test -d %s -a -f %s/bin/activate" % (self.path, self.path)
        positive = "source %s/bin/activate" % self.path
        negative = " && ".join([
            "virtualenv %s" % self.path,
            positive
            ])
        return test, positive, negative


class PkgProvider(object):
    """Base class for package handling"""
    def __init__(self, **kwargs):
        self.name = kwargs['name']
        self.version = kwargs['version']

    def revert(self):
        return None, None, None

    concrete_implementations = set()

    @classmethod
    def factory(cls, **kwargs):
        candidates = [provider for provider in cls.concrete_implementations
                      if provider.compatible_platform()]
        if len(candidates) < 1:
            raise RuntimeError("No concrete implementation available")
        if len(candidates) > 1:
            raise RuntimeError("More than one concrete implementation available")
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
                    '| grep "install ok installed*%s"') % (self.name, self.version)
            install = 'sudo apt-get install %s==%s' % (self.name, self.version)
        else:
            test = ('dpkg-query -W --showformat=\'${Status}\' %s '
                    '| grep "install ok installed"') % (self.name, self.version)
            install = 'sudo apt-get install %s' % (self.name, self.version)
        return test, None, install

    @staticmethod
    def compatible_platform():
        return platform.dist()[0] == 'Debian'

PkgProvider.concrete_implementations.add(DebPkgProvider)


class GitProvider(object):
    def __init__(self, **kwargs):
        self.path = kwargs['path']
        self.origin = kwargs['origin']
        self.ignore = []
        for ignore in kwargs.get('ignore', []):
            if ignore.startswith(self.path):
                self.ignore.append(ignore[len(self.path):])
            else:
                self.ignore.append(ignore)


    def provide(self):
        test = "test ! -d {0}".format(self.path)
        positive = "git clone {0} {1}".format(self.origin, self.path)
        # TODO handle ignore here
        negative = ["pushd {0}",
                    "git init",
                    "git remote add origin {1}",
                    "git checkout -t origin/master"
                    "popd"]
        negative = " && ".join(negative).format(self.path, self.origin)
        return test, positive, negative
