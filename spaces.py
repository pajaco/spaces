#!/usr/bin/env python

import sys, os, time
from spaces_config import config
from providers import providers
#from helpers import get_message, make_message
import SocketServer
import toposort
import ipdb
import re

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

def parse_result(data):
    parts = {}
    ctx = None
    for line in data.split("\n"):
        if line.startswith("STATUS"):
            parts['STATUS'] = line.split(" ", 1)[1].strip()
        elif line.startswith("STDOUT"):
            parts['STDOUT'] = []
            ctx = "STDOUT"
        elif line.startswith("STDERR"):
            parts['STDERR'] = []
            ctx = "STDERR"
        else:
            parts[ctx].append(line)

    return parts['STATUS'], parts['STDOUT'], parts['STDERR']

def is_provide_request(data):
    return data.startswith("PROVIDE")


class SpaceState(object):
    def __init__(self, cfg_file):
        self.providers = get_providers(get_config(cfg_file))

    def dispense(self, data):
        if data.startswith("PROVIDE"):
            self._providers = iter(self.providers)
            self._curr_provider = None
            self._curr_gen = None
            self._provision_type = 'provide'
        elif data.startswith("REVERT"):
            self._providers = iter(self.providers)
            self._curr_provider = None
            self._curr_gen = None
            self._provision_type = 'revert'

        if not self._curr_provider:
            try:
                self._curr_provider = self._providers.next()
            except StopIteration:
                return "END"
        if self._curr_gen is None:
            method = getattr(self._curr_provider, self._provision_type)
            self._curr_gen = method()
            cmd = self._curr_gen.next()
            return "DESC %s\n\nCMD %s" % (method.__doc__, cmd)
        else:
            try:
                return self._curr_gen.send(parse_result(data))
            except StopIteration:
                self._curr_provider = None
                self._curr_gen = None
                return self.dispense(data)


class SpacesTCPHandler(SocketServer.BaseRequestHandler):
    def setup(self):
        self.data = ""
    def handle(self):
        while True:
            data = self.request.recv(1024)
            if data == '':
                break
            self.data += data.strip()
            print "{} wrote: {}\n".format(self.client_address[0], data)

        out = self.server.state.dispense(self.data)
        self.request.send(out)

if __name__ == "__main__":
    cfg_file = sys.argv[1]
    HOST, PORT = "localhost", 5007
    server = SocketServer.TCPServer((HOST, PORT), SpacesTCPHandler)
    server.state = SpaceState(cfg_file)
    server.serve_forever()
