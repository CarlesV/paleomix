#!/usr/bin/python
#
# Copyright (c) 2013 Mikkel Schubert <MSchubert@snm.ku.dk>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
import os
import sys
import errno
import optparse
import logging


def initialize(config, template):
    """Takes an OptionParser object for which 'add_optiongroup' has
    been called, as well as a filename template (containing one '%i'
    field), and initializes logging for a pypeline.

    If --log-file has not been specified, the template is used to
    create a new logfile in --temp-root, skipping existing logfiles
    by incrementing the counter value. If a --log-file has been
    specified, this file is always created / opened."""
    global _INITIALIZED # pylint: disable=W0603
    if _INITIALIZED:
        raise RuntimeError("Attempting to initialize logging more than once")
    # Verify that the template is functional up front
    template % (1,) # pylint: disable=W0104

    root  = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(_PrintToConsole(logging.INFO))

    level = _LOGLEVELS[config.log_level]
    if config.log_file:
        handler = logging.FileHandler(config.log_file)
    else:
        handler = _LazyLogfile(config.temp_root, template)
    formatter = logging.Formatter("%s\n%%(asctime)s -- %%(levelname)s:\n%%(message)s" % ("-" * 60,))
    handler.setFormatter(formatter)
    handler.setLevel(level)
    root.addHandler(handler)

    _INITIALIZED = True


def add_optiongroup(parser):
    """Adds an option-group to an OptionParser object, with options
    pertaining to logging. Note that 'initialize' expects the config
    object to have these options."""
    group  = optparse.OptionGroup(parser, "Logging")
    group.add_option("--log-file", default = None,
                     help = "Write messages to this file. By default, a filename will be generated"
                            "using the template ${TEMP}/bam_pipeline_*.log, iff messages are logged"
                            "at or above the --log-level")
    group.add_option("--log-level", default = "warning", type = "choice",
                     choices = ("info", "warning", "error", "debug"),
                     help = "Log messages to log-file at and above the specified level [%default]")
    parser.add_option_group(group)


def get_logfile():
    return _LOGFILE


class _PrintToConsole(logging.Handler):
    """Logger that prints messages to the console using the
    pypeline.ui functions for colored text. Colors are blue
    for DEBUG, green for INFO (and unknown levels), yellow
    for WARNING, and red for ERROR and CRITICAL."""
    def __init__(self, level = logging.NOTSET):
        logging.Handler.__init__(self, level)

    def emit(self, record):
        func, stream = self.get_ui_function(record.levelno)
        func(record.getMessage(), file = stream)

    @classmethod
    def get_ui_function(cls, level):
        import pypeline.ui as ui

        if level in (logging.ERROR, logging.CRITICAL):
            return ui.print_err, sys.stderr
        elif level == logging.WARNING:
            return ui.print_warn, sys.stderr
        elif level == logging.DEBUG:
            return ui.print_debug, sys.stderr
        return ui.print_info, sys.stdout


class _LazyLogfile(logging.Handler):
    def __init__(self, folder, template):
        logging.Handler.__init__(self)
        self._folder   = folder
        self._template = template
        self._stream    = None
        self._handler   = None
        self._formatter = None


    def emit(self, record):
        if not self._handler:
            global _LOGFILE # pylint: disable = W0603
            _LOGFILE, self._stream = \
              _open_logfile(self._folder, self._template)
            self._handler = logging.StreamHandler(self._stream)
            self._handler.setFormatter(self._formatter)
        self._handler.emit(record)


    def flush(self):
        if self._handler:
            self._handler.flush()


    def setFormatter(self, form):
        logging.Handler.setFormatter(self, form)
        self._formatter = form


    def close(self):
        if self._handler:
            self._handler.close()
            self._stream.close()
            self._handler = None
            self._stream  = None


def _open_logfile(folder, template, start = 0):
    """Try to open a new logfile, taking steps to ensure that
    existing logfiles using the same template are not clobbered."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    while True:
        filename = os.path.join(folder, template % (start,))
        try:
            if not os.path.exists(filename):
                return filename, os.fdopen(os.open(filename, flags), "w")
        except OSError, error:
            if error.errno != errno.EEXIST:
                raise
        start += 1


_INITIALIZED = False
_LOGFILE     = None
_LOGLEVELS   = {
    'info'    : logging.INFO,
    'warning' : logging.WARNING,
    'error'   : logging.ERROR,
    'debug'   : logging.DEBUG,
}
