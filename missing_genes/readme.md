# missing_genes.py
Python script used to identify genes that are missing from a 'query' genome relative to a 'reference' genome.

Two different criteria are used to identify missing genes/features. A gene/feature is flagged as missing if either of the criteria is met.

    1. At least X proportion of a gene/feature's bases have 0x read depth coverage.
        - X is specified with '--maxZeroPerc'.
        - Default is 0.4 (i.e., 40%).
    2. The average depth of coverage across a gene/feature is less that Y % of the average coverage across the reference genome.
        - Y is specified with '--minAvgCov'.
        - Default is 0.01 (i.e., 1%). 

### Dependencies
- python
- bowtie2 (http://bowtie-bio.sourceforge.net/bowtie2/index.shtml)
- samtools (http://www.htslib.org/)


### Input

1. One or more **fastq files** with reads from the query to be mapped onto the reference

2. A **fasta file** for the reference genome

3. A **tab-delimited text file** with information about the location of genes/features in the reference genome
    - This file should contain one line for each gene/feature and each line should contain 5 columns in this order:
        1. Reference sequence name
        2. Locus Tag
        3. Gene Name (if available, E.g., dnaA)
        3. Start position of gene/feature (1-based) 
        4. End position of gene/feature (1-based)

### Usage

To get get usage info:
```
~/GDrive/scripts/missing_genes_v#.#.py  -h
```

Starting with a single fastq file:
```
~/GDrive/scripts/missing_genes_v#.#.py  -u file1.fastq  -r ref.fasta -g geneinfo.txt  -o outname
```

Starting with multiple fastq files:
```
~/GDrive/scripts/missing_genes_v#.#.py  -u file1.fastq,file2.fastq  -r ref.fasta -g geneinfo.txt -o outname
```

Starting with multiple fastq files:
```
~/GDrive/scripts/missing_genes_v#.#.py  -u file1.fastq,file2.fastq  -r ref.fasta -g geneinfo.txt -o outname
```

Starting with a bam file:
```
~/GDrive/scripts/missing_genes_v#.#.py  -b file.bam  -r ref.fasta -g geneinfo.txt -o outname
```


### Output

When starting from fastq(s), several output files will be generated. The primary output files of interest are (_outname_ used to specify the output string provided with '-o'):
    
    1. outname_missing_genes.txt
        - Tab-delimited file with a header line and 1 row per 'missing' gene/feature
        - Each row will contain 5 columns:
            1. Org_ID: Reference sequence name
            2. chrom_ID: Locus tag for gene/feature (will be empty if empty in input genes files)
            3. Gene: Gene name for gene/feature (will be empty if empty in input genes files)
            4. Perc_Zero_Cov: the % of gene/feature bases that have 0x read depth coverage
            5. Cov_Perc_Avg: the average level of read depth coverage across the gene/feature normalized to the average level of coverage across the entire genome.
        -All of these coverage stats are based on the pileup generated WITHOUT map quality filtering
        
    2. outname_repeat_in_ref_genes.txt
        - Tab-delimited file with a header line and 1 row per 'repeat' gene/feature (i.e., multi copies in the reference genome)
        -Same format as outname_missing_genes.txt, but reported stats are based on the pileup generated WITH map quality filtering

    3. outname_all_genes.txt
        - Tab-delimited file with a header line and 1 row per reference gene/feature
        - Each row will contain 7 columns:
            1. Org_ID: Reference sequence name
            2. chrom_ID: Locus tag for gene/feature (will be empty if empty in input genes files)
            3. Gene: Gene name for gene/feature (will be empty if empty in input genes files)
            4. Perc_Zero_Cov: the % of gene/feature bases that have 0x read depth coverage. (**NO map quality filtering**)
            5. Cov_Perc_Avg: the average level of read depth coverage across the gene/feature normalized to the average level of coverage across the entire genome. (**NO map quality filtering**)
            4. Qual_Perc_Zero_Cov: the % of gene/feature bases that have 0x read depth coverage. (**WITH map quality filtering**)
            5. Qual_Cov_Perc_Avg: the average level of read depth coverage across the gene/feature normalized to the average level of coverage across the entire genome. (**WITH map quality filtering**)
        -All of these coverage stats are based on the map quality filtered pileup

### Options

  ```
  -h, --help            show this help message and exit
  -u UNPAIRED, --unpaired=UNPAIRED
                        Fastq files with unpaired reads to be mapped to
                        reference. For this purpose, all files should be
                        treated as unpaired. You can combine the mapping of
                        multiple fastqs by entering them together as a comma
                        separated list [None]
  -r REF, --ref=REF     Fasta file that was used as reference in mapping.
                        [None, Required]
  -o OUT, --out=OUT     Base name for output files. Output files will be
                        written to the current working directory. [unknownID]
  --mapQ=MAPQ           Minimum mapping quality for a read to be used in the
                        pileup generation for the non-repeat version [20]
  --maxCov=MAXCOV       Max per base coverage to be used in the pileup
                        generation for the final quality check [500]
  --recursThresh=RECURSTHRESH
                        Minimum level of coverage required to change
                        consensus. [3000]
  --offset=OFFSET       Base quality offset used in the pileup. I believe the
                        default in samtools is Sanger(33) [33]
  --baseQual=BASEQUAL   Minimum base quality for a base to be counted when
                        looking at coverage. [20]
  --procs=PROCS         Number of processors to use in multi-threaded portions [16]
  --scoreMin=SCOREMIN   Minimum score for a good alignment in bowtie2. For
                        100bp reads, L,0,0=0mismatches, L,0,-0.06=1,
                        L,0,-0.12=2, L,0,-0.18=3, L,0,-0.24=4, L,0,-0.30=5,
                        L,0,-0.6=10. [L,0,-0.12]
  -b BAM, --bam=BAM     Bam file from previous run. **Optional starting place. [None]
  -s SAM, --sam=SAM     Sam file from previous run. **Optional starting place. [None]
  -p STD_PILE, --std_pile=STD_PILE
                        Basic pileup from previous run. **Optional starting place. [None]
  --qual_pile=QUAL_PILE
                        Pileup from previous run that only contains high
                        quality mapped reads. **Optional starting place.
                        [None]
  --miss_regions=MISS_REGIONS
                        Missing regions file from previous run. **Optional
                        starting place. This automatically throws the
                        --justGenes flag. [None]
  -g GENES, --genes=GENES
                        Gene info for the reference strain [None, REQD]
  --justGenes           Use this flag if you already have the missing regions
                        file and you just want to find the genes that
                        correspond
  --maxZeroPerc=MAXZEROPERC
                        If a gene has a larger percent of bases with zero
                        coverage than this, it is considered missing [0.4]
  --minAvgCov=MINAVGCOV
                        If a gene has a lower percent of average coverage than
                        this, it is considered missing [0.01]
  ```



Copyright (C) 2017  Jason Ladner

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
