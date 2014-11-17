import csv
import re

class ParseError(Exception):
    def __init__(self, orig, lineno, message, filename='unknown file'):
        self.orig = orig
        self.lineno = lineno
        self.message = message
        self.filename = filename

    def __str__(self):
        return "ParseError: line %d |%s| %s in %s\n" % (self.lineno,
                                                        self.orig,
                                                        self.message,
                                                        self.filename)

class Definition(object):
    def __init__(self, labels):
        self.labels = labels
        self.options = {}

    def __hash__(self):
        return hash(self.labels)

class DefinitionParser(object):
    special_keys = ["_require", "_provider"]
    SECTION = 'section'
    OPTION = 'option'
    OPTION_CT = 'option cont'
    EMPTY = 'empty'
    COMMENT = 'comment'
    EOF = 'eof'

    def __init__(self):
        self._tree = {}
        self._dependency = {}

    def _parse_section(lnum, orig, line):
        pass

    def get_required(self):
        required = []
        for section, options in self._tree:
            pass

    def read(self, instream, filename=None):
        self._preprocessed = self._preprocess(instream)
        curr_section = None
        prev_section = None
        curr_option = None
        prev_option = None
        prev_sect_lnum = None
        prev_sect_orig = None
        for i, (lnum, orig, line, ltype) in enumerate(self._preprocessed):
            if ltype == self.SECTION:
                prev_section = curr_section
                curr_option = None
                if line[-1] != ']':
                    raise ParseError(orig, lnum, "Bad section syntax")
                if len(line) < 3:
                    raise ParseError(orig, lnum, "No labels in section")
                line = line[1:-1]
                curr_section = tuple([label for label in line.split(" ")
                    if label])
                if curr_section == prev_section:
                    raise ParseError(orig, lnum, "Duplicate section")
                if prev_section and not self._tree[prev_section]:
                    raise ParseError(prev_sect_orig, prev_sect_lnum,
                            "Section without options")
                self._preprocessed[i].append(curr_section)
                self._tree[curr_section] = {}
                self._dependency[curr_section] = set()
                prev_sect_lnum = lnum
                prev_sect_orig = orig

            elif ltype == self.OPTION:
                prev_option = curr_option
                if not curr_section:
                    raise ParseError(orig, lnum, "Option not within section")
                curr_option, vals = [elem.strip() for elem in line.split(":", 1)]
                if not (curr_option or curr_option in self.special_keys \
                        or curr_option.isalpha()):
                    raise ParseError(orig, lnum, "Option key must only contain alpha chars")
                if curr_option == prev_option:
                    raise ParseError(orig, lnum, "Duplicate option %s" % curr_option)
                if not vals:
                    raise ParseError(orig, lnum, "Option '%s' has no values" % curr_option)
                vals = [v.strip() for v in list(csv.reader([vals]))[0]]
                if curr_option == '_require':
                    vals = self._parse_required_values(vals)
                    self._dependency[curr_option] = vals
                self._tree[curr_section][curr_option] = vals

            elif ltype == self.OPTION_CT:
                if not vals:
                    raise ParseError(
                            orig, lnum,
                            "Option '%s' has continuation with no value" % curr_option)
                vals = [v.strip() for v in list(csv.reader([vals]))[0]]
                if curr_option == '_require':
                    vals = self._parse_required_values(vals)
                    self._dependency[curr_option] = vals
                self._tree[curr_section][curr_option] = vals

            elif ltype == self.EOF:
                if curr_section and not self._tree[curr_section]:
                    raise ParseError(prev_sect_orig, prev_sect_lnum,
                            "Section without options")

        print self._tree
        print self._dependency

    def _parse_required_values(self, values):
        required = set()
        for val in values:
            if val[0] != '[' or val[-1] != ']':
                raise ParseError(orig, lnum,
                    "Special '_require' option's value '%s' is invalid" % (val))
            required.add(tuple([r.strip() for r in val[1:-1].split(" ")]))
        return required

    def _preprocess(self, instream):
        # remove leading whitespace from section lines and option lines
        # unwrap those that have no option name in them (continuations)
        preprocessed = []
        acc = []
        for lnum, line in enumerate(instream.split("\n"), 1):
            acc.append(lnum)
            acc.append(line) # store orig line
            line = line.split('#')[0].strip() # chop off comments and whitespace
            acc.append(line) # store processed line
            if not len(line):
                acc.append(self.EMPTY)
            elif re.match(r'\s*\[', line):
                acc.append(self.SECTION)
            elif re.match(r'\s*\S+:', line):
                acc.append(self.OPTION)
            else: # continuation line
                acc.append(self.OPTION_CT)
            preprocessed.append(acc)
            acc = []
        # sort out end of file
        preprocessed.append([-1, '', '', self.EOF])
        # and turn upside down again
        return preprocessed


class SpaceDefinition(object): 
    def __init__(self, config):
        self._parser = CascadingConfigParser()
        self._parser.parse(config)
        self._definition = {}

    def get_definitions(self):
        # only get definitions that don't extend another or those that are
        # required by other
        #import ipdb; ipdb.set_trace()
        dep_tree = {}
        raw_sections = self._parser.sections()
        sections = [section.split(" ") for section in raw_sections]
        for section in sections:
            dep_tree[tuple(section)] = {"extended_by": set(),
                                        "required": set()}
        for section in sections:
            _section = section[:]
            while len(_section):
                _section.pop()
                if _section in sections:
                    extended_by = dep_tree[tuple(section)]["extended_by"]
                    extended_by.add(tuple(_section))
        for section in sections:
            try:
                for required in self._parser.getlist(section, '_require'):
                    assert required[0] == '['
                    assert required[-1] == ']'
                    assert len(required[1:-1]) > 0
                    required = dep_tree[tuple(section)]["required"]
                    required.add(tuple(required[1:-1].split(" ")))
            except NoOptionError:
                pass
        print dep_tree



if __name__ == "__main__":
    config = """
    [a]
        _require: [b]

    [a b]
        _require: [c]
    [c]
    d: ad
    """
    #spacedef = SpaceDefinition(config)
    #spacedef.read(config)
    #import ipdb; ipdb.set_trace()
    #print spacedef.get_definitions()
    defparser = DefinitionParser()
    defparser.read(config)



