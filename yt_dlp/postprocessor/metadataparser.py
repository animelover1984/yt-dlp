import re

from enum import Enum

from .common import PostProcessor


class MetadataParserPP(PostProcessor):
    class Actions(Enum):
        INTERPRET = 'interpretter'
        REPLACE = 'replacer'

    def __init__(self, downloader, actions):
        PostProcessor.__init__(self, downloader)
        self._actions = []
        for f in actions:
            action = f[0]
            assert isinstance(action, self.Actions)
            self._actions.append(getattr(self, action._value_)(*f[1:]))

    @classmethod
    def validate_action(cls, action, *data):
        ''' Each action can be:
                (Actions.INTERPRET, from, to) OR
                (Actions.REPLACE, field, search, replace)
        '''
        if not isinstance(action, cls.Actions):
            raise ValueError(f'{action!r} is not a valid action')
        getattr(cls, action._value_)(cls, *data)

    @staticmethod
    def field_to_template(tmpl):
        if re.match(r'[a-zA-Z_]+$', tmpl):
            return f'%({tmpl})s'
        return tmpl

    @staticmethod
    def format_to_regex(fmt):
        r"""
        Converts a string like
           '%(title)s - %(artist)s'
        to a regex like
           '(?P<title>.+)\ \-\ (?P<artist>.+)'
        """
        if not re.search(r'%\(\w+\)s', fmt):
            return fmt
        lastpos = 0
        regex = ''
        # replace %(..)s with regex group and escape other string parts
        for match in re.finditer(r'%\((\w+)\)s', fmt):
            regex += re.escape(fmt[lastpos:match.start()])
            regex += rf'(?P<{match.group(1)}>.+)'
            lastpos = match.end()
        if lastpos < len(fmt):
            regex += re.escape(fmt[lastpos:])
        return regex

    def run(self, info):
        for f in self._actions:
            f(info)
        return [], info

    def interpretter(self, inp, out):
        def f(info):
            outtmpl, tmpl_dict = self._downloader.prepare_outtmpl(template, info)
            data_to_parse = self._downloader.escape_outtmpl(outtmpl) % tmpl_dict
            self.write_debug(f'Searching for r{out_re.pattern!r} in {template!r}')
            match = out_re.search(data_to_parse)
            if match is None:
                self.report_warning('Could not interpret {inp!r} as {out!r}')
                return
            for attribute, value in match.groupdict().items():
                info[attribute] = value
                self.to_screen('Parsed %s from %r: %r' % (attribute, template, value if value is not None else 'NA'))

        template = self.field_to_template(inp)
        out_re = re.compile(self.format_to_regex(out))
        return f

    def replacer(self, field, search, replace):
        def f(info):
            val = info.get(field)
            if val is None:
                self.report_warning(f'Video does not have a {field}')
                return
            elif not isinstance(val, str):
                self.report_warning(f'Cannot replace in field {field} since it is a {type(val).__name__}')
                return
            self.write_debug(f'Replacing all r{search!r} in {field} with {replace!r}')
            info[field], n = search_re.subn(replace, val)
            if n:
                self.to_screen(f'Changed {field} to: {info[field]}')
            else:
                self.to_screen(f'Did not find r{search!r} in {field}')

        search_re = re.compile(search)
        return f


class MetadataFromFieldPP(MetadataParserPP):
    @classmethod
    def to_action(cls, f):
        match = re.match(r'(?P<in>.*?)(?<!\\):(?P<out>.+)$', f)
        if match is None:
            raise ValueError(f'it should be FROM:TO, not {f!r}')
        return (
            cls.Actions.INTERPRET,
            match.group('in').replace('\\:', ':'),
            match.group('out'))

    def __init__(self, downloader, formats):
        MetadataParserPP.__init__(self, downloader, [self.to_action(f) for f in formats])


class MetadataFromTitlePP(MetadataParserPP):  # for backward compatibility
    def __init__(self, downloader, titleformat):
        MetadataParserPP.__init__(self, downloader, [(self.Actions.INTERPRET, 'title', titleformat)])
