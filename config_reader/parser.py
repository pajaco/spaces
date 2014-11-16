"""Configuration parser for ini-based format that allows composition of
definitions from separate sections cascade-style. It is based on ConfigParser
module and provides the same interface + extensions

    For example the following input:

        [a b c]
        var1: val1
        [a]
        var2: val2
        [a b]
        var3: val3

    can be seen as:
        [a b]
        var1: val1
        var2: val2
        var3: val3

The cascading rule assumes that each section name is composed of one or more
strings(labels). If a given key isn't found in the section queried for
(eg. [a b c]) then a subsequent query is done for the same key in it's related
sections (here first [a b] and if no success then [a]).
"""

import ConfigParser
import csv


class NoOptionError(ConfigParser.Error):
    """A requested option was not found."""

    def __init__(self, option, section, other_sections):
        parent_sections = ", ".join([repr(ps) for ps in other_sections])
        msg = ("No option %r in section: %r nor in its parent%s: %s" %
               (option, section, 's' if len(other_sections) > 1 else '',
                parent_sections))
        ConfigParser.Error.__init__(self, msg)
        self.option = option
        self.section = section
        self.parent_sections = other_sections
        self.args = (option, section, other_sections)


class CascadingConfigParser(object):
    """
    Wrapper class for any parser in ConfigParser module. Default parser is
    RawConfigParser
    """
    def __init__(self, config_parser=None):
        self._config_parser = config_parser or ConfigParser.RawConfigParser()

    def __getattr__(self, name):
        attr = self.__dict__.get(name)
        if attr:
            return attr
        attr = self._config_parser.__dict__.get(name)
        if hasattr(self._config_parser, name):
            return getattr(self._config_parser, name)
        raise AttributeError("'%s' object has no attribute '%s'" % (
            self.__class__, name))



    def get(self, section, option, cascade=False):
        """
        Get value for option in section.
        Optionally search in related sections
        """
        orig_section = section
        try:
            return self._config_parser.get(section, option)
        except ConfigParser.NoOptionError:
            if not cascade:
                raise
        parent_sections = []
        while True:
            _section = section.rsplit(" ", 1)[0]
            if section == _section:
                break
            section = _section
            parent_sections.append(section)
            try:
                return self._config_parser.get(section, option)
            except ConfigParser.NoSectionError:
                pass
            except ConfigParser.NoOptionError:
                pass
        raise NoOptionError(option, orig_section, parent_sections)

    def items(self, section, cascade=False):
        """
        Get option names and values pairs in section.
        Optionally search in related sections
        """
        items = self._config_parser.items(section)
        keys = [item[0] for item in items]
        if cascade:
            while True:
                _section = section.rsplit(" ", 1)[0]
                if section == _section:
                    break
                section = _section
                try:
                    for item in self._config_parser.items(section):
                        if item[0] not in keys:
                            items.append(item)
                except ConfigParser.NoSectionError:
                    pass
        return items

    def options(self, section, cascade=False):
        """
        Get a list of option names for the given section name.
        Optionally search in related sections
        """
        options = set(self._config_parser.options(section))
        if cascade:
            while True:
                _section = section.rsplit(" ", 1)[0]
                if section == _section:
                    break
                section = _section
                try:
                    for option in self._config_parser.options(section):
                        options.add(option)
                except ConfigParser.NoSectionError:
                    pass
        return list(options)

    def getlist(self, section, option, cascade=False):
        """
        Get a value of an option in a section as a list.
        Value is parsed CSV style where comma is the delimiter.
        """
        raw = self.get(section, option, cascade)
        vals = list(csv.reader(raw.splitlines()))[0]
        return [v.strip() for v in vals]
