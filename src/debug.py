# -*- coding: iso-8859-1 -*-
# -----------------------------------------------------------------------------
# debug.py - Debugger for kaa applications
# -----------------------------------------------------------------------------
# kaa.base - The Kaa Application Framework
# Copyright 2013 Dirk Meyer, Jason Tackaberry, et al.
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
from __future__ import absolute_import

# python imports
import os
import time
import sys
import struct
import atexit
import socket
import inspect

# kaa.base imports
from .utils import tempfile
from . import nf_wrapper as notifier


socket_listen = None
socket_trace = None

python_distribution = '%s/lib/python%s.%s' % (sys.prefix, sys.version_info.major, sys.version_info.minor)

def socket_unlink():
    """
    Delete the debug socket for this application
    """
    if os and os.path.exists(tempfile('.debug/%s' % os.getpid())):
        os.unlink(tempfile('.debug/%s' % os.getpid()))

def socket_trace_close():
    """
    Close the trace socket
    """
    global socket_trace
    if socket_trace:
        print '=== STOP TRACE ==='
        sys.settrace(None)
        socket_trace.close()
        socket_trace = None

def socket_trace_send(frame, event, arg):
    """
    Callback for sys.settrace
    """
    if event in ('return', 'call'):
        filename = frame.f_code.co_filename
        if filename.startswith(__file__):
            # do not trace the debugging module itself
            return
        if filename.startswith(python_distribution) and not filename.find('packages') > 0:
            # do not trace python core (lib except dist-packages and site-packages)
            return
        try:
            socket_trace.send('\n')
        except:
            socket_trace_close()
            return
    if event in ('line', 'call'):
        tb = inspect.getframeinfo(frame)
        msg = '[%2.2f %s %s:%3d] %s\n' % \
            (time.time(), event, tb.filename, tb.lineno, tb.code_context[0].rstrip())
        if event == 'call' and tb.code_context[0].strip().startswith('def '):
            args = ','.join('%s=%s' % i for i in frame.f_locals.items() if i[0] != 'self')
            msg = msg.rstrip() + ' with ' + args + '\n'
        try:
            socket_trace.send(msg)
        except:
            socket_trace_close()
            return
    return socket_trace_send

def new_command(s):
    """
    New command from the debugging socket
    """
    notifier.socket_remove(s, 0)
    cmd = s.recv(struct.unpack('!I', s.recv(4))[0]).strip().split(' ')
    if cmd[0] == 'trace':
        global socket_trace
        if socket_trace:
            socket_trace_close()
        socket_trace = s
        print '=== START TRACE ==='
        sys.settrace(socket_trace_send)
    if cmd[0] == 'winpdb':
        s.send('ok\n')
        s.close()
        socket_trace_close()
        print '=== START WINPDB EMBEDDED DEBUGGER ==='
        import rpdb2; rpdb2.start_embedded_debugger('kaa')

def new_connection(s):
    """
    New connection on the debugging socket
    """
    notifier.socket_add(socket_listen.accept()[0], new_command, 0)
    return True

def init():
    """
    Set up the debugging module by opening the unix socket
    """
    global socket_listen
    if socket_listen:
        notifier.socket_remove(socket_listen, 0)
    else:
        atexit.register(socket_unlink)
    socket_unlink()
    socket_listen = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    socket_listen.bind(tempfile('.debug/%s' % os.getpid()))
    socket_listen.listen(1)
    notifier.socket_add(socket_listen, new_connection, 0)
