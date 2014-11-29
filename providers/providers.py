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


class EnvProvider(object):
    """Provide setting and exporting environment variables"""
    def __init__(self, space, **kwargs):
        self.space = space
        self.description = None
        self._env_vars = kwargs
        self.bac_preamble = "_SPACES_%s_" % self.space

    def get_description(self):
        if self.description:
            return self._description
        return ":".join([self.__doc__, ", ".join(self._env_vars.keys())])

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
            test = "env | grep \"%s%s\"" % (self.bac_preamble, k)
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
        self.ignore = []  # private ignore, goes to .git/info/exclude
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


class ScriptGenerator(object):
    def __init__(self, *providers):
        self.providers = providers or []
        self.silent = False

    def _marshall_script_parts(self, data):
        if data is None:
            return [("true", "true", "false")]
        if isinstance(data, tuple):
            data = [data]
        marshalled = []
        for datum in data:
            if len(datum) == 1:
                datum = ["true", datum[0], "false"]
            elif len(datum) == 2:
                datum = [datum[0], datum[1], "false"]
            else:
                datum = list(datum)
            if not isinstance(datum[0], str):
                datum[0] = "true"
            if not isinstance(datum[1], str):
                datum[1] = "true"
            if not isinstance(datum[2], str):
                datum[1] = "false"
            marshalled.append(datum)

        return data

    step_template = """if step-test "{steptest}"; then
    step-desc "{stepprimarydesc}"
    step "{stepprimary}"
else
    step-desc "{stepalterndesc}"
    step-do "{stepaltern}"
fi

if step-revert; then
    if step-test "{revtest}";
    then
        step-desc "{revprimarydesc}"
        step "{revprimary}"
    else
        step-desc "{revalterndesc}"
        step-do "{revaltern}"
    fi
fi
step-end
    """
    def _write_step_template(self, **kwargs):
        placeholders = {'steptest': 'true',
                        'stepprimary': 'true',
                        'stepprimarydesc': '',
                        'stepalterndesc': '',
                        'stepaltern': 'false',
                        'revtest': 'true',
                        'revprimarydesc': '',
                        'revprimary': 'true',
                        'revalterndesc': '',
                        'revaltern': 'false'}
        for k, v in kwargs.items():
            if isinstance(v, str):
                placeholders[k] = v.replace('"', '\\\"')
        return self.step_template.format(**placeholders)

    def _build_step(self, provide, revert):
        out = []
        for i in range(len(provide)):
            step_test, step_primary, step_alter = provide[i]
            rev_test, rev_primary, rev_alter = revert[i]
            _out = self._write_step_template(steptest=step_test,
                                             stepprimary=step_primary,
                                             stepaltern=step_alter,
                                             revtest=rev_test,
                                             revprimary=rev_primary,
                                             revaltern=rev_alter,)
            out.append(_out)
        return out

    def build(self):
        out = []
        for provider in self.providers:
            out.append("#BLOCK")
            try:
                out.append("block-desc \"%s\"" % provider.get_description())
            except AttributeError:
                out.append("block-desc \"%s block\"" % type(provider).__name__)
            provide = self._marshall_script_parts(provider.provide())
            try:
                revert = self._marshall_script_parts(provider.revert())
            except AttributeError:
                revert = [("true", "true", "false")] * len(provide)
            try:
                check_dep = provider.check_dependency()
                out.append("block-require-test \"%s\"" % check_dep)
            except AttributeError:
                pass
            out.extend(self._build_step(provide, revert))

        return "\n".join(out)

if __name__ == "__main__":
    # TODO integration tests make more sense but for now...
    env_provider = EnvProvider('testspace', A='$TMP/blah', TMP='/tmp')
    provided = env_provider.provide()
    expected = [('test -z "$TMP"', 'export TMP=/tmp',
                 '_SPACES_testspace_TMP=$TMP && export TMP=/tmp'),
                ('test -z "$A"', 'export A=$TMP/blah',
                 '_SPACES_testspace_A=$A && export A=$TMP/blah')]
    assert expected == provided
    reverted = env_provider.revert()
    expected = [('env | grep _SPACES_testspace_TMP',
                 ('export TMP=$_SPACES_testspace_TMP; '
                  'unset _SPACES_testspace_TMP'),
                 'unset _SPACES_testspace_TMP'),
                ('env | grep _SPACES_testspace_A',
                 ('export A=$_SPACES_testspace_A; '
                  'unset _SPACES_testspace_A'),
                 'unset _SPACES_testspace_A'), ]
    #assert expected == reverted

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
                 'git clone git@github.com/pajaco/spaces ~/spaces', None),
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

    builder = ScriptGenerator(env_provider, venv_provider, git_provider)
    #builder.silent = True
    print builder.build()
                                   
