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

from copy import deepcopy

from pypeline.node import \
    CommandNode, \
    MetaNode
from pypeline.atomiccmd.command import \
    AtomicCmd
from pypeline.atomiccmd.sets import \
    ParallelCmds
from pypeline.atomiccmd.builder import \
    create_customizable_cli_parameters, \
    use_customizable_cli_parameters, \
    AtomicCmdBuilder, \
    apply_options
from pypeline.nodes.samtools import \
    GenotypeNode, \
    TabixIndexNode, \
    FastaIndexNode, \
    BAMIndexNode, \
    MPileupNode
from pypeline.nodes.bedtools import \
    SlopBedNode
from pypeline.nodes.sequences import \
    ExtractReferenceNode
from pypeline.common.fileutils import \
    swap_ext, \
    add_postfix

import pypeline.tools.factory as factory


################################################################################
################################################################################
## Genotyping specific nodes
## TODO: Move to pypeline.nodes

class VCFPileupNode(CommandNode):
    @create_customizable_cli_parameters
    def customize(cls, reference, in_bam, in_vcf, outfile, dependencies=()):
        cat = factory.new("cat")
        cat.add_value("%(IN_VCF)s")
        cat.set_kwargs(IN_VCF=in_vcf,
                       OUT_STDOUT=AtomicCmd.PIPE)

        vcfpileup = AtomicCmdBuilder(["vcf_create_pileup", "%(OUT_PILEUP)s"],
                                     IN_REF=reference,
                                     IN_BAM=in_bam,
                                     IN_STDIN=cat,
                                     OUT_PILEUP=outfile,
                                     OUT_TBI=outfile + ".tbi")
        vcfpileup.add_value("%(IN_BAM)s")
        vcfpileup.set_option("-f", "%(IN_REF)s")

        return {"commands": {"cat": cat,
                             "pileup": vcfpileup}}

    @use_customizable_cli_parameters
    def __init__(self, parameters):
        commands = parameters.commands
        commands = [commands[key].finalize() for key in ("cat", "pileup")]
        description = "<VCFPileup: '%s' -> '%s'>" % (parameters.in_bam,
                                                     parameters.outfile)
        CommandNode.__init__(self,
                             description=description,
                             command=ParallelCmds(commands),
                             dependencies=parameters.dependencies)


class VCFFilterNode(CommandNode):
    @create_customizable_cli_parameters
    def customize(cls, pileup, infile, outfile, regions, dependencies=()):
        cat = factory.new("cat")
        cat.add_value("%(IN_VCF)s")
        cat.set_kwargs(IN_VCF=infile,
                       OUT_STDOUT=AtomicCmd.PIPE)

        vcffilter = AtomicCmdBuilder(["vcf_filter"],
                                     IN_PILEUP=pileup,
                                     IN_STDIN=cat,
                                     OUT_STDOUT=AtomicCmd.PIPE)

        vcffilter.add_option("--pileup", "%(IN_PILEUP)s")
        for contig in regions["HomozygousContigs"]:
            vcffilter.add_option("--homozygous-chromosome", contig)

        bgzip = AtomicCmdBuilder(["bgzip"],
                                 IN_STDIN=vcffilter,
                                 OUT_STDOUT=outfile)

        return {"commands": {"cat": cat,
                             "filter": vcffilter,
                             "bgzip": bgzip}}

    @use_customizable_cli_parameters
    def __init__(self, parameters):
        commands = [parameters.commands[key].finalize()
                    for key in ("cat", "filter", "bgzip")]

        description = "<VCFFilter: '%s' -> '%s'>" % (parameters.infile,
                                                     parameters.outfile)
        CommandNode.__init__(self,
                             description=description,
                             command=ParallelCmds(commands),
                             dependencies=parameters.dependencies)


class BuildRegionsNode(CommandNode):
    @create_customizable_cli_parameters
    def customize(cls, options, infile, regions, outfile, padding,
                  dependencies=()):
        params = AtomicCmdBuilder(["vcf_to_fasta"],
                                  IN_VCFFILE=infile,
                                  IN_TABIX=infile + ".tbi",
                                  IN_INTERVALS=regions["BED"],
                                  OUT_STDOUT=outfile)
        params.set_option("--padding", padding)
        params.set_option("--genotype", "%(IN_VCFFILE)s")
        params.set_option("--intervals", "%(IN_INTERVALS)s")
        if regions["ProteinCoding"]:
            params.set_option("--whole-codon-indels-only")
        if not regions["IncludeIndels"]:
            params.set_option("--ignore-indels")

        return {"command": params}

    @use_customizable_cli_parameters
    def __init__(self, parameters):
        command = parameters.command.finalize()
        description = "<BuildRegions: '%s' -> '%s'>" % (parameters.infile,
                                                        parameters.outfile)
        CommandNode.__init__(self,
                             description=description,
                             command=command,
                             dependencies=parameters.dependencies)


class SampleRegionsNode(CommandNode):
    @create_customizable_cli_parameters
    def customize(cls, infile, bedfile, outfile, dependencies=()):
        params = AtomicCmdBuilder(["bam_sample_regions"],
                                  IN_PILEUP=infile,
                                  IN_INTERVALS=bedfile,
                                  OUT_STDOUT=outfile)
        params.set_option("--genotype", "%(IN_PILEUP)s")
        params.set_option("--intervals", "%(IN_INTERVALS)s")

        return {"command": params}

    @use_customizable_cli_parameters
    def __init__(self, parameters):
        command = parameters.command.finalize()

        description = "<SampleRegions: '%s' -> '%s'>" \
            % (parameters.infile, parameters.outfile)

        CommandNode.__init__(self,
                             description=description,
                             command=command,
                             dependencies=parameters.dependencies)


################################################################################
################################################################################

# Caches for nodes shared between multiple tasks
_BAI_CACHE = {}
_FAI_CACHE = {}
_BED_CACHE = {}
_VCF_CACHE = {}


def build_bam_index_node(bamfile):
    """Returns a node generating a BAI index (using SAMTools) for a BAM file;
    the result is cached, to ensure that multiple calls for the same BAM does
    not result in files being clobbered.

    """
    if bamfile not in _BAI_CACHE:
        _BAI_CACHE[bamfile] = \
            BAMIndexNode(infile=bamfile)
    return _BAI_CACHE[bamfile]


def build_fasta_index_node(reference):
    if reference not in _FAI_CACHE:
        _FAI_CACHE[reference] = \
            FastaIndexNode(infile=reference)
    return _FAI_CACHE[reference]


def build_regions_nodes(regions, padding, dependencies=()):
    destination = add_postfix(regions["BED"], ".padded_%ibp" % (padding,))

    if not padding:
        return regions["BED"], dependencies

    if destination not in _BED_CACHE:
        dependencies = list(dependencies)
        dependencies.append(build_fasta_index_node(regions["FASTA"]))
        _BED_CACHE[destination] \
            = SlopBedNode(genome=regions["FASTA"] + ".fai",
                          infile=regions["BED"],
                          outfile=destination,
                          from_start=padding,
                          from_end=padding,
                          dependencies=dependencies)

    return destination, _BED_CACHE[destination]


def _apply_vcf_filter_options(vcffilter, genotyping, sample):
    filter_cfg = genotyping["VCF_Filter"]
    apply_options(vcffilter.commands["filter"], filter_cfg)
    if filter_cfg["MaxReadDepth"][sample]:
        max_depth = filter_cfg["MaxReadDepth"][sample]
        vcffilter.commands["filter"].set_option("--max-read-depth", max_depth)
    return vcffilter.build_node()


def build_genotyping_bedfile_nodes(options, genotyping, sample, regions,
                                   dependencies):
    bamfile = "%s.%s.bam" % (sample, regions["Prefix"])
    bamfile = os.path.join(options.samples_root, bamfile)
    if regions["Realigned"]:
        bamfile = add_postfix(bamfile, ".realigned")

    prefix = regions["Genotypes"][sample]
    padding, bedfile, node = genotyping["Padding"], None, dependencies
    if not genotyping["GenotypeEntirePrefix"]:
        bedfile, node = \
            build_regions_nodes(regions, padding, dependencies)
        bai_node = build_bam_index_node(bamfile)
        dependencies = (node, bai_node)
    else:
        prefix = os.path.join(os.path.dirname(prefix),
                              "%s.%s.TEMP" % (sample, regions["Prefix"]))

    return prefix, bamfile, bedfile, dependencies


def build_genotyping_nodes_cached(options, genotyping, sample, regions,
                                  dependencies):
    """Carries out genotyping, filtering of calls, and indexing of files for a
    given sample and prefix. If the option 'GenotypeEntirePrefix' is enabled,
    the BAM is genotyped once, and each set of RegionsOfInterest simply extract
    the relevant regions during construction of the consensus sequence.

    Parameters:
        options: An options object (c.f. pypeline.tools.phylo_pipeline.config).
        genotyping: Genotyping options defined for a specific set of areas of
                    interest, corresponding to Genotyping:NAME in the makefile.
        sample: The name of the sample to be genotyped.
        egions: A dictionary for a 'RegionsOfInterest' from the makefile.
        dependencies: Depenencies that must be met before genotyping starts.

    Returns a tuple containing the filename of the filtered and tabix-indexed
    VCF file, and the top-level node generating this file. Multiple calls for
    the same BAM and prefix will return the same VCF and nodes if the option
    for 'GenotypeEntirePrefix' is enabled, otherwise each ROI is genotyped
    individiually.

    Output files are generated in ./results/PROJECT/genotyping. If the option
    for 'GenotypeEntirePrefix' is enabled, the following files are generated:
        SAMPLE.PREFIX.vcf.bgz: Unfiltered calls for variant/non-variant sites.
        SAMPLE.PREFIX.vcf.pileup.bgz: Pileup of sites containing SNPs.
        SAMPLE.PREFIX.vcf.pileup.bgz.tbi: Tabix index of the pileup.
        SAMPLE.PREFIX.filtered.vcf.bgz: Variant calls filtered using vcf_filter.
        SAMPLE.PREFIX.filtered.vcf.bgz.tbi: Tabix index for the filtered VCF.

    If 'GenotypeEntirePrefix' is not enabled for a given ROI, the following
    files are generated for that ROI (see descriptions above):
        SAMPLE.PREFIX.ROI.filtered.vcf.bgz
        SAMPLE.PREFIX.ROI.filtered.vcf.bgz.tbi
        SAMPLE.PREFIX.ROI.vcf.bgz
        SAMPLE.PREFIX.ROI.vcf.pileup.bgz
        SAMPLE.PREFIX.ROI.vcf.pileup.bgz.tbi

    In addition, the following files are generated for each set of
    RegionsOfInterest (ROI), regardless of the 'GenotypeEntirePrefix' option:
        SAMPLE.PREFIX.ROI.CDS.fasta: FASTA sequence of each feature in the ROI.
        SAMPLE.PREFIX.ROI.CDS.fasta.fai: FASTA index generated using SAMTools.

    """
    output_prefix, bamfile, bedfile, dependencies \
        = build_genotyping_bedfile_nodes(options, genotyping, sample, regions,
                                         dependencies)

    if (bamfile, output_prefix) in _VCF_CACHE:
        return _VCF_CACHE[(bamfile, output_prefix)]

    calls = swap_ext(output_prefix, ".vcf.bgz")
    pileups = swap_ext(output_prefix, ".vcf.pileup.bgz")
    filtered = swap_ext(output_prefix, ".filtered.vcf.bgz")

    # 1. Call samtools mpilup | bcftools view on the bam
    genotype = GenotypeNode.customize(reference=regions["FASTA"],
                                      regions=bedfile,
                                      infile=bamfile,
                                      outfile=calls,
                                      dependencies=dependencies)
    apply_options(genotype.commands["pileup"], genotyping["MPileup"])
    apply_options(genotype.commands["genotype"], genotyping["BCFTools"])
    genotype = genotype.build_node()

    # 2. Collect pileups of sites with SNPs, to allow proper filtering by
    #    frequency of the minor allele, as only the major non-ref allele is
    #    counted in the VCF (c.f. field DP4).
    vcfpileup = VCFPileupNode.customize(reference=regions["FASTA"],
                                        in_bam=bamfile,
                                        in_vcf=calls,
                                        outfile=pileups,
                                        dependencies=genotype)
    apply_options(vcfpileup.commands["pileup"], genotyping["MPileup"])
    vcfpileup = vcfpileup.build_node()

    # 3. Filter all sites using the 'vcf_filter' command
    vcffilter = VCFFilterNode.customize(infile=calls,
                                        pileup=pileups,
                                        outfile=filtered,
                                        regions=regions,
                                        dependencies=vcfpileup)
    vcffilter = _apply_vcf_filter_options(vcffilter, genotyping, sample)

    # 4. Tabix index. This allows random-access to the VCF file when building
    #    the consensus FASTA sequence later in the pipeline.
    tabix = TabixIndexNode(infile=filtered,
                           preset="vcf",
                           dependencies=vcffilter)

    _VCF_CACHE[(bamfile, output_prefix)] = (filtered, tabix)
    return filtered, tabix


def build_genotyping_nodes(options, genotyping, sample, regions, dependencies):
    """Builds the nodes required for genotyping a BAM, in part or in whole.

    By default, only the region of interest (including padding) will be
    genotyped. However, if option 'GenotypeEntirePrefix' is enabled, the entire
    genome is genotyped, and reused between different areas of interest.

    In addition to the files generated by 'build_genotyping_nodes_cached', this
    function generates the following files:
        SAMPLE.PREFIX.ROI.fasta: FASTA containing each named region.
        SAMPLE.PREFIX.ROI.fasta.fai: Index file built using "samtools faidx"

    The function returns a sequence of the top-level nodes generating the files.

    """
    # 1. Get path of the filtered VCF file, and the assosiated node
    filtered, node = build_genotyping_nodes_cached(options=options,
                                                   genotyping=genotyping,
                                                   sample=sample,
                                                   regions=regions,
                                                   dependencies=dependencies)

    # 2. Generate consensus sequence from filtered VCF
    output_fasta = regions["Genotypes"][sample]
    builder = BuildRegionsNode(options=options,
                               infile=filtered,
                               regions=regions,
                               outfile=output_fasta,
                               padding=genotyping["Padding"],
                               dependencies=node)

    # 3. Index sequences to make retrival easier for MSA
    faidx = FastaIndexNode(infile=output_fasta,
                           dependencies=builder)

    return (faidx,)


def build_sampling_nodes(options, genotyping, sample, regions, dependencies):
    fasta_file = regions["Genotypes"][sample]
    pileup_file = swap_ext(fasta_file, ".pileup.bgz")

    padding = genotyping["Padding"]
    slop, node = build_regions_nodes(regions, padding, dependencies)

    bam_file = "%s.%s.bam" % (sample, regions["Prefix"])
    bam_file = os.path.join(options.samples_root, bam_file)
    if regions["Realigned"]:
        bam_file = add_postfix(bam_file, ".realigned")
    bai_node = build_bam_index_node(bam_file)

    genotype = MPileupNode(reference=regions["FASTA"],
                           regions=slop,
                           infile=bam_file,
                           outfile=pileup_file,
                           dependencies=(node, bai_node))
    tabix = TabixIndexNode(infile=pileup_file,
                           preset="pileup",
                           dependencies=genotype)

    builder = SampleRegionsNode(infile=pileup_file,
                                bedfile=regions["BED"],
                                outfile=fasta_file,
                                dependencies=tabix)

    faidx = FastaIndexNode(infile=fasta_file,
                           dependencies=builder)

    return (faidx,)


def build_reference_nodes(options, genotyping, sample, regions, dependencies):
    input_file = "%s.%s.fasta" % (regions["Prefix"], sample)
    input_fpath = os.path.join(options.refseq_root, input_file)

    output_file = "%s.%s.fasta" % (sample, regions["Desc"])
    output_fpath = os.path.join(options.destination, "genotypes", output_file)

    dependencies = list(dependencies)
    dependencies.append(build_fasta_index_node(regions["FASTA"]))

    node = ExtractReferenceNode(reference=input_fpath,
                                bedfile=regions["BED"],
                                outfile=output_fpath,
                                dependencies=dependencies)

    faidx = FastaIndexNode(infile=output_fpath,
                           dependencies=node)
    return (faidx,)


# Functions used to carry out each of the supported genotyping methods
_GENOTYPING_METHODS = {
    "reference sequence": build_reference_nodes,
    "random sampling": build_sampling_nodes,
    "samtools": build_genotyping_nodes,
}


def build_sample_nodes(options, genotyping, regions_sets, sample,
                       dependencies=()):
    nodes = []
    for regions in regions_sets.itervalues():
        regions = deepcopy(regions)

        # Enforce homozygous contigs based on gender tag
        regions["HomozygousContigs"] \
            = regions["HomozygousContigs"][sample["Gender"]]

        genotyping_method = sample["GenotypingMethod"].lower()
        if genotyping_method not in _GENOTYPING_METHODS:
            assert False, "Unexpected genotyping method %r for sample %r" \
                          % (genotyping_method, sample["Name"])

        genotyping_function = _GENOTYPING_METHODS[genotyping_method]
        node = genotyping_function(options=options,
                                   genotyping=genotyping[regions["Name"]],
                                   sample=sample["Name"],
                                   regions=regions,
                                   dependencies=dependencies)
        nodes.extend(node)

    return MetaNode(description=sample["Name"],
                    dependencies=nodes)


def chain(pipeline, options, makefiles):
    destination = options.destination
    for makefile in makefiles:
        regions_sets = makefile["Project"]["Regions"]
        genotyping = makefile["Genotyping"]
        options.destination = os.path.join(destination,
                                           makefile["Project"]["Title"])

        nodes = []
        for sample in makefile["Project"]["Samples"].itervalues():
            nodes.append(build_sample_nodes(options, genotyping, regions_sets,
                                            sample, makefile["Nodes"]))

        makefile["Nodes"] = tuple(nodes)
    options.destination = destination
