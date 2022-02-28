import os

os.environ['EVENTLET_NO_GREENDNS'] = 'yes'  # noqa E402

import eventlet  # noqa
eventlet.monkey_patch()
# Monkey patch the original current_thread to use the up-to-date _active
# global variable. See https://bugs.launchpad.net/bugs/1863021 and
# https://github.com/eventlet/eventlet/issues/592
import __original_module_threading as orig_threading  # noqa
import threading  # noqa
orig_threading.current_thread.__globals__['_active'] = threading._active
