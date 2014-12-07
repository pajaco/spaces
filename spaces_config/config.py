"""
Regular ini rules, except:
    special settings:
        _use: those will be marked as dependencies of the current section
        _provider: the python provider that creates shell commands

    keys can have no value
    values can be lists (whitespace is separator)
    values can contain references to other sections and particular keys in them
"""


from ConfigParser import (ConfigParser, NoOptionError, Error,
                          NoSectionError, MAX_INTERPOLATION_DEPTH)
import re


class SpacesConfigParser(ConfigParser):
    _USES_OPT = "_uses"
    _PROVIDER_OPT = "_provider"

    def gettuple(self, section, option):
        value = self.get(section, option)
        return list(filter(None, (x.strip() for x in value.splitlines())))

    def getuses(self, section):
        out = []
        try:
            for uses in self.gettuple(section, self._USES_OPT):
                if uses[0] == '[':
                    uses = uses[1:]
                if uses[-1] == ']':
                    uses = uses[:-1]
                if not self.has_section(uses):
                    raise NoSectionError(uses)
                out.append(uses)
        except NoOptionError:
            pass

        # now those used for interpolation
        for o, v in self.items(section, raw=True):
            m = self._KEYCRE.match(v)
            if m.group(1):
                if not self.has_section(m.group(1)):
                    raise NoSectionError(m.group(1))
                out.append(m.group(1))

        return set(out)

    def getprovider(self, section):
        return self.get(section, self._PROVIDER_OPT)

    def _interpolate(self, section, option, rawval, vars):
        # do the string interpolation
        value = rawval
        depth = MAX_INTERPOLATION_DEPTH
        while depth:                    # Loop through this until it's done
            depth -= 1
            if value and "[" in value:
                value = self._KEYCRE.sub(self._interpolation_replace, value)
                try:
                    value = value % vars
                except KeyError, e:
                    raise InterpolationMissingOptionError(
                        option, section, rawval, e.args[0])
            else:
                break
        if value and "%(" in value:
            raise InterpolationDepthError(option, section, rawval)
        return value

    _KEYCRE = re.compile(r"\[([^\]]*)\]:(\S+)|.")

    def _interpolation_replace(self, match):
        s = match.group(1)
        if s is None:
            return match.group()
        elif self.has_section(s):
            o = match.group(2)
            if o is None:
                return match.group()
            # try exact match
            if self.has_option(s, o):
                return self.get(s, o)

            # try partial; longest first
            for option in reversed(sorted(self.options(s))):
                if o.startswith(option):
                    v = self.get(s, option, raw=True)
                    return v + o[len(option):]
            raise NoOptionError(s, o)
        else:
            raise NoSectionError(s)



if __name__ == "__main__":
    from StringIO import StringIO
    cfg = """
[test section 1]
testkeya:   1
testkeyb:   a
            b
_provider: BlahProvider

[test section 2]
#_uses: [test section 1]
testkeya: [test section 1]:testkeyafoo
testkeyb: [test section 1]:testkeyb
_provider: FooProvider
"""

    config = SpacesConfigParser(allow_no_value=True)
    config.readfp(StringIO(cfg), 'cfg')
    #print config.sections()
    #print config.items('test section 1')
    #print config.items('test section 2')
    #print config.gettuple('test section 2', 'testkeya')
    #print config.gettuple('test section 2', 'testkeyb')
    #print config.gettuple('test section 1', 'testkeyb')
    #print config.gettuple('test section 1', 'testkeya')
    print config.getuses('test section 1')
    print config.getuses('test section 2')
    #print config.getprovider('test section 1')
    #print config.getprovider('test section 2')
