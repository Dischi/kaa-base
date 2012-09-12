# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# httpserver.py - Simple HTTP server based on kaa
# -----------------------------------------------------------------------------
# This module provides a RequestHandler and a TCPServer that together
# work as simple HTTP server for kaa.
#
# -----------------------------------------------------------------------------
# Copyright 2012 Dirk Meyer
#
# Please see the file AUTHORS for a complete list of authors.
#
# This library is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License version
# 2.1 as published by the Free Software Foundation.
#
# This library is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301 USA
#
# -----------------------------------------------------------------------------

# python imports
import os
import logging
import BaseHTTPServer
import SocketServer
import shutil
import urlparse

# kaa imports
import kaa
from .. import nf_wrapper as notifier

# get logging object
log = logging.getLogger('kaa')

class ThreadedHTTPRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    """
    RequestHandler.
    """

    def do_GET(self):
        """
        Serve a GET request.
        """
        callback = None
        parse_result = urlparse.urlparse(self.path)
        for path, callback in self.server._get_handler:
            if path == parse_result.path or \
                    (parse_result.path.startswith(path) and path.endswith('/')):
                path = parse_result.path[len(path):]
                break
        else:
            callback = None
        if not callback:
            if self.path in self.server._static:
                self.send_response(200)
                self.end_headers()
                f = open(self.server._static[self.path])
                shutil.copyfileobj(f, self.wfile)
                f.close()
                return
            abspath = os.path.abspath(self.path)
            for path, dirname in self.server._directories:
                if abspath.startswith(path):
                    fname = os.path.join(dirname, abspath[len(path)+1:])
                    if os.path.isfile(fname):
                        self.send_response(200)
                        self.end_headers()
                        f = open(fname)
                        shutil.copyfileobj(f, self.wfile)
                        f.close()
                        return
            self.send_response(404)
            self.end_headers()
            return
        try:
            attributes = {}
            for key, value in urlparse.parse_qs(parse_result.query).items():
                if isinstance(value, (list, tuple)):
                    if len(value) == 0:
                        attributes[key] = True
                    elif len(value) == 1:
                        attributes[key] = value[0]
                    else:
                        attributes[key] = value
                else:
                    attributes[key] = value
            ctype, content = kaa.MainThreadCallable(callback)(path, **attributes).wait()
        except:
            self.send_response(500)
            log.exception('server error')
            return
        self.send_response(200)
        self.send_header("Content-type", ctype)
        self.send_header("Content-Length", len(content))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        """
        Dump log messages to the used logging object
        """
        log.info(format, *args)


class HTTPServer(SocketServer.ThreadingTCPServer):
    """
    HTTPServer

    Example::

      server = kaa.net.httpserver.HTTPServer(("", port), MyRequestHandler)
      server.serve_forever()  # hooks into kaa mainloop

      def callback1(path):
          '''
          callback1 handles GET /foo
          '''
          return 'text/plain', 'foo was called'

      @kaa.coroutine()
      def callback2(path):
          '''
          callback2 handles GET /bar/ as well as /bar/something
          '''
          yield waitforsomething
          yield 'text/plain', 'bar was called with ' + path

      # add callback1 and callback2 to the server
      server.add_handler('foo', callback1)
      server.add_handler('bar/', callback2)

    """
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address, RequestHandlerClass=ThreadedHTTPRequestHandler, bind_and_activate=True):
        """
        Create the HTTPServer
        """
        self._get_handler = []
        self._static = {}
        self._directories = []
        SocketServer.ThreadingTCPServer.__init__(self, server_address, RequestHandlerClass, bind_and_activate)

    def __handle_request(self, f):
        """
        Wrapper around _handle_request_noblock for pynotifier
        """
        self._handle_request_noblock()
        return True

    def serve_forever(self):
        """
        Hook the server into pynotifier
        """
        notifier.socket_add(self.fileno(), self.__handle_request)

    def add_handler(self, path, callback):
        """
        Add a handler for path
        """
        self._get_handler.append((path, callback))

    def add_static(self, path, filename):
        """
        Add a static page from filename
        """
        if os.path.isdir(filename):
            self._directories.append((path, filename))
        else:
            self._static[path] = filename
