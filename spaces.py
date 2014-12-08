import sys, os, time
from spaces_config import config
from providers import providers
import toposort
import ipdb

reserved_option_names = ['_uses', '_provider']



def sort_sections(config):
    graph = {}
    for section in config.sections():
        graph[section] = config.getuses(section)
    return toposort.toposort_flatten(graph)



def get_providers(config):
    _providers = []
    sorted_sections = sort_sections(config)
    for sect in sorted_sections:
        provider = getattr(providers, config.getprovider(sect))
        params = {}
        for opt in config.options(sect):
            if opt not in reserved_option_names:
                val = config.gettuple(sect, opt)
                if len(val) == 1:
                    val = val[0]
                params[opt] = val
        _providers.append(provider(params))
    return _providers
        

if __name__ == "__main__":
    file_name = sys.argv[1]
    _config = config.SpacesConfigParser(allow_no_value=True)
    _config.readfp(open(sys.argv[1]))
    print get_providers(_config)
