#!/usr/bin/env python3

from imp import reload
from re import findall
from collections import OrderedDict
from os.path import dirname, join
from logging import getLogger, FileHandler, Formatter

import connect
from config import get_config
from plugin_handler import PluginHandler
from sys import argv

class MessageData:
    
    def __init__(self):
        self.irc_cmd = None
        self.to = None
        self.from_nick = None
        self.from_host = None
        #self.channel = None    # replaced by self.to
        self.tokens = None
        self.string = None
        self.regex_match = None

    def copy(self):
        new = MessageData()
        new.irc_cmd = self.irc_cmd
        new.to = self.to
        new.from_nick = self.from_nick
        new.from_host = self.from_host
        new.tokens = self.tokens
        new.string = self.string
        new.regex_match = self.regex_match
        return new


class HandlerLib:
    
    """This class contains functions for handling various IRC events."""
    
    def __init__(self, bot):
        self.bot = bot
        self.ident = bot.ident
        self.conn = bot.conn
        self.plugin_handler = bot.plugin_handler
    
    def handle_connect(self, data):
        """
        Called once we have connected to and identified with the server.
        Mainly joins the channels that we want to join at the start.
        """
        for chan in self.bot.joins:
            self.conn.join(chan)
    
    def handle_nick_in_use(self, data):
        self.ident.nick += '_'
        self.conn.connect()
    
    def handle_ping(self, data):
        self.plugin_handler.exec_hooks('ping', None, data)

    def handle_join(self, data):
        if data.from_nick != self.ident.nick:
            self.plugin_handler.exec_other_join(data)
        else:
            self.plugin_handler.exec_self_join(data)

    
    def handle_privmsg(self, data):
        
        self.plugin_handler.exec_privmsg_re_if_exists(data)
        self.plugin_handler.exec_privmsg(data)
        # Always call exec_cmd_if_exists last, as it alters
        # data.tokens
        self.plugin_handler.exec_cmd_if_exists(data)
        
        # This has to be changed
        """ Old code
        if is_to_me and (cmd in self.cmds.addr_funcs):
            self.cmds.addr_funcs[cmd](args, data)
        elif cmd in self.cmds.unaddr_funcs:
            self.cmds.unaddr_funcs[cmd](args, data)
        else:
            for func in self.cmds.all_privmsg_funcs:
                func(tokens, data)
            for pattern in self.cmds.regex_funcs:
                groups = findall(pattern, ' '.join(tokens))
                if groups:
                    self.cmds.regex_funcs[pattern](groups)
        """
        
    def handle_nick(self, data):
        if data.from_nick != self.ident.nick:
            self.plugin_handler.exec_hooks('other_nick_change', '', data)
    
    def handle(self, data):
        """This is the function that is called externally.  It decides
        which handler should be used and calls that handler."""
        cmd = data.irc_cmd
        if cmd == '433':    # nick already in use
            handler = self.handle_nick_in_use
        elif cmd == '376':    # end of MOTD
            handler = self.handle_connect
        elif cmd == 'PING':
            handler = self.handle_ping
        elif cmd == 'ERROR':
            handler = self.handle_errors
        elif cmd == 'JOIN':
            data.to = data.tokens.pop(0)
            handler = self.handle_join
        elif cmd == 'PRIVMSG':
            data.to = data.tokens.pop(0)
            # If message is to me, pretend "channel" is the sender
            if data.to == self.ident.nick:
                data.to = data.from_nick
            handler = self.handle_privmsg
        elif cmd == 'NICK':
            data.to = data.tokens.pop(0)
            handler = self.handle_nick
        else:
            handler = lambda d: True    # this is probably not the best 
        handler(data)

class Identity:

    def __init__(self, vals):
        self.host = vals['host']
        self.serv = vals['server']
        self.ident = vals['ident']
        self.name = vals['name']
        self.nick = vals['nick']

class Bot:

    valid_hooks = {
            'command',
            'privmsg_re'
            # TODO: implement more
            }
    
    def __init__(self, config):
        self.config = config
        self.ident = Identity(config['identity'])
        self.joins = config['channels']['join'].split()
        self.hooks = {hook_type: OrderedDict() for hook_type in self.valid_hooks}
        self.conn = connect.IRCConn(self)
        self.plugin_handler = PluginHandler(self, join(dirname(__file__), 'plugins'))
        self.handlers = HandlerLib(self)
        self.conn.connect()
        try:
            self.conn.mainloop()
        except BaseException as e:
            self.handle_exception(e)

    def handle_exception(self, e):
        raise e
    
    def parse(self, line):
        if not line:
            # empty line; this should throw up an error.
            return
        line = line.strip('\r\n')
        tokens = line.split()
        if tokens[0].startswith(':'):
            # Not sure if this if-else is necessary, as possibly lines
            # always start with ":"
            prefix = tokens.pop(0)[1:].strip(':')
        else:
            prefix = ''
        
        cmd = tokens.pop(0)

        # Maybe best to create MessageData here??
        data = MessageData()
        data.irc_cmd = cmd
        try:
            data.from_nick, data.from_host = prefix.split('!')
        except ValueError:
            pass
                    
        data.tokens = tokens
        data.string = ' '.join(tokens)
        self.handlers.handle(data)

    
    def reload_cmds(self):
        self.cmds = reload(config).CommandLib(self)
        
def main(*args):
    if not args:
        print('You must at least specify a host server to connect to.')
        return 1
    host = args[0]
    cfgdir = join(dirname(__file__), 'configs')
    conf = get_config(cfgdir, host)
    if conf is None:
        print('No config file found or config file incomplete.')
        return 1
    Bot(conf)

if __name__ == '__main__':
    main(*argv[1:])
