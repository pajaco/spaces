import sys, os, time
from spaces_config import config
from providers import providers
import toposort
import ipdb

reserved_option_names = ['_uses', '_provider']

def get_config(filepath):
    cfg = config.SpacesConfigParser(allow_no_value=True)
    cfg.readfp(open(filepath))
    return cfg

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

def send_error(pipe, error):
    with open(pipe, 'w') as stream:
        print "Sending: %s" % error
        stream.write('ERR %s' % error)

def send_end(pipe):
    with open(pipe, 'w') as stream:
        print "Sending: END"
        stream.write('END')

def send_command(pipe, command):
    with open(pipe, 'w') as stream:
        print "Sending: CMD %s" % command
        stream.write('CMD %s' % command)

def send_info(pipe, info):
    with open(pipe, 'w') as stream:
        print "Sending: INF %s" % info
        stream.write('INF %s' % info)

def receive_command(pipe):
    with open(pipe, 'r') as stream:
        data = stream.readline()[:-1]
        if not data.startswith('CMD ') or data[4:] not in ['provide', 'revert']:
            pass  #TODO handle error
        print "Received: %s" % data
        return data[4:]

def receive_status(pipe):
    with open(pipe, 'r') as stream:
        data = stream.readline()[:-1]
        if not data.startswith('XST '):
            pass  #TODO handle error
        print "Received: %s" % data
        return int(data[4:])

def receive_stdout(pipe):
    with open(pipe, 'r') as stream:
        data = stream.readline()[:-1]
        if not data.startswith('STO '):
            pass  #TODO handle error
        print "Received: %s" % data
        return data[4:]

def receive_stderr(pipe):
    with open(pipe, 'r') as stream:
        data = stream.readline()[:-1]
        if not data.startswith('STE '):
            pass  #TODO handle error
        print "Received: %s" % data
        return data[4:]

if __name__ == "__main__":
    cfg_file = sys.argv[1]
    in_pipe = sys.argv[2]
    out_pipe = sys.argv[3]

    providers = get_providers(get_config(cfg_file))
    space_cmd = receive_command(in_pipe)
    for provider in providers:
        fn = getattr(provider, space_cmd)
        send_info(out_pipe, fn.__doc__)
        cmd_gen = fn()
        # first command goes without passing data back
        send_command(out_pipe, cmd_gen.next())
        while True:
            rcode = receive_status(in_pipe)
            stdout = receive_stdout(in_pipe)
            stderr = receive_stderr(in_pipe)
            try:
                send_command(out_pipe, cmd_gen.send((rcode, stdout, stderr)))
            except StopIteration:
                #TODO handle last rcode, stdout, stderr
                break
            
    send_end(out_pipe)


