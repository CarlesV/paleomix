#!/usr/bin/python
#
# Copyright (c) 2012 Mikkel Schubert <MSchubert@snm.ku.dk>
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

from pypeline.node import \
     CommandNode, \
     MetaNode
from pypeline.atomiccmd.command import \
     AtomicCmd
from pypeline.atomiccmd.builder import \
     AtomicCmdBuilder, \
     use_customizable_cli_parameters, \
     create_customizable_cli_parameters


# Presets mainly taken from
# http://mafft.cbrc.jp/alignment/software/algorithms/algorithms.html
_PRESETS = {
    "mafft"    : ["mafft"],
    "auto"     : ["mafft", "--auto"],
    "fft-ns-1" : ["fftns", "--retree", 1],
    "fft-ns-2" : ["fftns"],
    "fft-ns-i" : ["fftnsi"],
    "nw-ns-i"  : ["nwnsi"],
    "l-ins-i"  : ["linsi"],
    "e-ins-i"  : ["einsi"],
    "g-ins-i"  : ["ginsi"],
    }



class MAFFTNode(CommandNode):
    @create_customizable_cli_parameters
    def customize(cls, input_file, output_file, algorithm = "auto", dependencies = ()):
        command = AtomicCmdBuilder(_PRESETS[algorithm.lower()])
        command.add_value("--quiet")
        command.add_value("%(IN_FASTA)s")
        command.set_kwargs(IN_FASTA   = input_file,
                           OUT_STDOUT = output_file)

        return {"command"      : command,
                "dependencies" : dependencies}


    @use_customizable_cli_parameters
    def __init__(self, parameters):
        description = "<MAFFTNode (%s): '%s' -> '%s'>" \
                % (parameters.algorithm,
                   parameters.input_file,
                   parameters.output_file)

        CommandNode.__init__(self,
                             command      = parameters.command.finalize(),
                             description  = description,
                             dependencies = parameters.dependencies)
