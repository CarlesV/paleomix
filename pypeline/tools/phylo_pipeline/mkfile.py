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
import sys


_TEMPLATE = """# -*- mode: Yaml; -*-
Project:
  Title: PROJECT_NAME

  # List of samples to be included in the analytical steps, which may be
  # grouped using any arbitrary number of (levels of) groups. (Sub)groups
  # are not required, but may be used instead of listing individual samples
  # in 'ExcludeSamples' and 'FilterSingletons'.
  Samples:
    <GROUP>:
      <SUBGROUP>:
        SAMPLE_NAME:
          # The species name of a sample (not required)
          SpeciesName: ...
          # The common name of a sample (not required)
          CommonName:  ...
          # Gender of the sample; used to filter SNPs on homozygous
          # contigs (see below). Any name may be used for the genders.
          Gender:       ...
          # Method to use when genotyping samples (see 'Genotyping');
          # defaults to 'SAMTools' if not explicitly specified.
          Genotyping Method: ...

  # Specifies a set of regions of interest, each representing one or more
  # named regions in a reference sequence (e.g. genes) in BED format.
  RegionsOfInterest:
     NAME:
       # Name of the prefix; is expected to correspond to the filename
       # of the FASTA file without the extension / the name of the
       # prefix used in the BAM pipeline.
       Prefix: PREFIX_NAME
       # If true, BAM files are expected to have the postfix ".realigned";
       # allows easier interopterability with the BAM pipeline.
       Realigned: no
       # Specifies whether or not the sequences are protein coding; if true
       # indels are only included in the final sequence if the length is
       # divisible by 3.
       ProteinCoding: no
       # Do not include indels in final sequence; note that indels are still
       # called, and used to filter SNPs. Requires that 'MultipleSequenceAlignment' is enabled
       IncludeIndels: yes
       # List of contigs for which heterozygous SNPs should be filtered
       # (site set to 'N'); e.g. chrX for 'Male' humans, or chrM, etc.
#       HomozygousContigs:
#         GENDER_NAME:
#          - CONTIG_NAME_1

  # Filter sites in a sample, replacing any nucleotide not observed
  # in the specified list of samples or groups with 'N'.
#  FilterSingletons:
#    NAME_OF_SAMPLE:
#      - <NAME_OF_GROUP>
#      - NAME_OF_SAMPLE


Genotyping:
  # Regions of interest are expanded by this number of bases when calling
  # SNPs, in order to ensure that adjacent indels can be used during filtering
  # (VCF_filter --min-distance-to-indels and --min-distance-between-indels).
  # The final sequences does not include the padding.
  Padding: 10

  # Settings for genotyping by random sampling of nucletoides at each site
  Random:
    # Min distance of variants to indels
    --min-distance-to-indels: 2

  MPileup:
    -E: # extended BAQ for higher sensitivity but lower specificity
    -A: # count anomalous read pairs

  BCFTools:
    -g: # Call genotypes at variant sites

  VCF_Filter:
    # Maximum coverage acceptable for genotyping calls
    # If zero, the default vcf_filter value is used
    MaxReadDepth: 0

    # Minimum coverage acceptable for genotyping calls
    --min-read-depth: 8
    # Min RMS mapping quality
    --min-mapping-quality: 10
    # Min QUAL score (Phred) for genotyping calls
    --min-quality: 30
    # Min distance of variants to indels
    --min-distance-to-indels: 2
    # Min distance between indels
    --min-distance-between-indels: 10
    # Min P-value for strand bias (given PV4)
    --min-strand-bias: 1.0e-4
    # Min P-value for baseQ bias (given PV4)
    --min-baseq-bias: 1.0e-4
    # Min P-value for mapQ bias (given PV4)
    --min-mapq-bias: 1.0e-4
    # Min P-value for end distance bias (given PV4)
    --min-end-distance-bias: 1.0e-4
    # Max frequency of the major allele at heterozygous sites
    --min-allele-frequency: 0.2


MultipleSequenceAlignment:
  # Multiple sequence alignment using MAFFT
  MAFFT:
    # Select alignment algorithm; valid values are 'mafft', 'auto', 'fft-ns-1',
    # 'fft-ns-2', 'fft-ns-i', 'nw-ns-i', 'l-ins-i', 'e-ins-i', and 'g-ins-i'.
    Algorithm: G-INS-i

    # Parameters for mafft algorithm; see above for example of how to specify
    --maxiterate: 1000


PhylogeneticInference:
  PHYLOGENY_NAME:
    # Exclude (groups of) samples from this analytical step
#    ExcludeSamples:
#      - <NAME_OF_GROUP>
#      - NAME_OF_SAMPLE

    # If 'yes', a tree is generated per named sequence in the areas of
    # interest; otherwise a super-matrix is created from the combined set
    # of regions specfied below.
    PerGeneTrees: no

    # Which Regions Of Interest to build the phylogeny from.
    RegionsOfInterest:
       REGIONS_NAME:
         # Partitioning scheme for sequences: Numbers specify which group a
         # position belongs to, while 'X' excludes the position from the final
         # partioned sequence; thus "123" splits sequences by codon-positions,
         # while "111" produces a single partition per gene. If set to 'no',
         # a single partition is used for the entire set of regions.
         Partitions: "111"
         # Limit analysis to a subset of a RegionOfInterest; subsets are expected to be
         # located at <genome root>/<prefix>.<region name>.<subset name>.names, and
         # contain single name (corresponding to column 4 in the BED file) per line.
         SubsetRegions: SUBSET_NAME

    ExaML:
      # Number of times to perform full phylogenetic inference
      Replicates: 1
      # Number of bootstraps to compute
      Bootstraps: 100
      Model: GAMMA


PAML:
   # Run codeml on each named sequence in the regions of interest
  codeml:
#   Exclude (groups of) samples from this analytical step
#    ExcludeSamples:
#      - <NAME_OF_GROUP>
#      - NAME_OF_SAMPLE

    # Root the final tree(s) on one or more samples; if no samples
    # are specified, the tree(s) will be rooted on the midpoint(s)
#    RootTreesOn:
#      - <NAME_OF_GROUP>
#      - NAME_OF_SAMPLE

    # Limit analysis to a subset of a RegionOfInterest; subsets are expected to be
    # located at <genome root>/<prefix>.<region name>.<subset name>.names, and
    # contain single name (corresponding to column 4 in the BED file) per line.
#    SubsetRegions:
#      REGIONS_NAME: SUBSET_NAME

    # One or more 'codeml' runs; name is used as a postfix for results.
    RUN_NAME:
      # Control file template; the values 'seqfile', 'treefile'
      # automatically set to the approriate values.
      ControlFile: PATH_TO_CODEML_CONTROL_FILE
      # 'treefile' in the control-file is set to this value
      TreeFile:    PATH_TO_CODEML_TREEFILE
"""


def main(_argv):
    print _TEMPLATE

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
