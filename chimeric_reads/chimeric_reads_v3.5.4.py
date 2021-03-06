#!/usr/bin/env python

# By Jason Ladner

#This script looks for single reads that are chimeric, with different portions mapping to different regions

#In v2, I tweaked the way I was making the plot in matplot lib to try to make it easy to create a legend
#In v3, Fixed bug related to reads with doubly aligned bases. Only counted the left most alignments
#   **** Known issue related with mutations (I think) near breakpoints, that lead to unaligned, internal bases. This could be accounted for, but it's unclear whether bases should be added to left or right.
#In v3.1, Slightly changed the way the sizes for the legend circles is calculated to avoid non-integers
#In v3.2, Added option to batch process sam/bam files mapped to the same reference. Also, fixed issue that would raise an error if only 1 unique deletion was detected
#In v3.3, Started pulling info from sam/bam file about reference lengths to set x,y limits, instead of using the right most deletion coordinate
#In v3.4, Added screen to make sure that both alignments are in the same orientation. Also started to flag putative duplicates, and allow for these to not be included in counts for plots
#In v3.5, Added screen to make msure that reads are only considered if they are not "second in pair"
#In v3.5.1, Added some more checks to quantify different types of reads
#In v3.5.2, Fixed bug in calculating mapped query bases for reads mapped to the reverse strand, a bug in calculating missing bases for inverted alignments with multiply mapped bases and some other small bugs
    #Now, added a 2nd version of the aligned_pairs for which the query coordinates will be flipped for reads mapped to the reverse strand in order for rev and for alignments to be properly compared
#In v3.5.3, Added functionality for better characterizing bases that are included in both alignments of a chimeric read
#In v3.5.4, Cleaned up the output printed to the screen while running. Started calculating the % of chimeric reads (SA, only 2 alignments, >=opts.minPerc bases aligned when considering both reads), made it the default to only graph reads with alignments consistent with simple deletions (same ref, same strand, full, correct orientation) 

#*#*#*# Need to examine how "matches_only" affects behavior

from __future__ import division
import sys, optparse, os, pysam, math
import numpy as np
from scipy.stats import gaussian_kde

#For plotting
import matplotlib
matplotlib.use('PDF')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties as fp
fontP = fp()


def main():

    #To parse command line
    usage = "usage: %prog [options]"
    p = optparse.OptionParser(usage)
    
    p.add_option('-i', '--input', help='File with info for bulk processing. Should be tab-delimited, 2 columns: 1) sam/bam file and 2) base string for output files. [None, OPT]')
    p.add_option('-b', '--bam', help='input _c  sam or bam file. [None, OPT]')
    p.add_option('-o', '--out', help='Base string for output files. Will only be used with -b option for running a single sam/bam. [None, OPT]')
    p.add_option('-m', '--minPerc', type='float', default=0.99, help='Minumum percent of query read that must be aligned to the reference, when considering all alignemnts. [0.99]')
    p.add_option('-r', '--orient', default='correct', help='Specifies which orientation of alignments will be graphed and summarized in output files. Options: "correct" and "inverted" [correct]')
    p.add_option('--filterDups', default = False, action='store_true', help='Use this flag if you do not want to include putative duplicate counts in the figures that are generated. [None, OPT]')
    
    opts, args = p.parse_args()

    if opts.bam and opts.out: process_bam(opts.bam, opts.out, opts)
    if opts.input:
        for line in open(opts.input, 'r'):
            cols=line.strip().split('\t')
            process_bam(cols[0], cols[1], opts)

###-----------------End of main()--------------------------->>>

#Reads through a bam file, identifies chimeric reads, creates several outputs summarizing those chimeras, including a plot
def process_bam(bamname, outname, opts):

    #One key for every mapped read that has a secondary alignment (and is R1, as currently written)
    #Keys are lists of lists with info about the different alignments
    SA_info = {}
    #One key for every ref, values are dicts. One key for every mapped readname, values are lists of % read bases aligned (or matched). One entry in list for each alignment. True = reverse strand, False = forward (NO R1 filter at the moment!!!)
    all_aligned = {}
    #One key for every read, values are dicts. One key for ref read is aligned to, values are lists of True/False. One entry in list for each alignment. True = reverse strand, False = forward (NO R1 filter at the moment!!!)
    all_align_flip = {}
    #Create an Alignment File object using pysam
    bam = pysam.AlignmentFile(bamname)

    #Make dict with read length info
    #!#!#! This could potentially cause a problem is the sam/bam file does not include a header with info on reference lengths
        #!#!#! I should probably update this section to include a warning and work around if this is the case
    reflen_dict={}
    for index, r in enumerate(bam.references):
        reflen_dict[r]=bam.lengths[index]

    #Step through all of the reads
    for read in bam.fetch():
        #To keep track of all mapped reads
        if not read.is_unmapped: 
            if read.reference_name not in all_aligned: all_aligned[read.reference_name]={}
            if read.query_name not in all_aligned[read.reference_name]: all_aligned[read.reference_name][read.query_name]=[]

            if read.query_name not in all_align_flip: all_align_flip[read.query_name]={}
            if read.reference_name not in all_align_flip[read.query_name]: all_align_flip[read.query_name][read.reference_name]=[]
            all_align_flip[read.query_name][read.reference_name].append(read.is_reverse)
        
            #Find chimeric reads
            #Check to make sure that 1) the read has a supplementary alignment AND 2) that it is not read 2
            if read.has_tag("SA"):
                if not read.is_read2:
                    #Add read name to dict if not already present
                    if read.query_name not in SA_info: SA_info[read.query_name]=[]
            
                    #Checks for hard clipped bases, and corrects pairs and length for this, if present
                    if 5 in [x[0] for x in read.cigartuples]:
                        corr_pairs, corr_length = corr_hardclipped(read)
                        #Add info about this alignment
                        all_aligned[read.reference_name][read.query_name].append(len(corr_pairs)/corr_length)
                        if read.is_reverse: SA_info[read.query_name].append([read.reference_name, corr_length, corr_pairs, read.cigarstring, read.is_reverse, flip(corr_pairs, corr_length)])
                        else: SA_info[read.query_name].append([read.reference_name, corr_length, corr_pairs, read.cigarstring, read.is_reverse, corr_pairs])

                    else:
                        #Add info about this alignment
                        all_aligned[read.reference_name][read.query_name].append(len(read.get_aligned_pairs(matches_only=True))/read.infer_query_length())
                        if read.is_reverse: SA_info[read.query_name].append([read.reference_name, read.infer_query_length(), read.get_aligned_pairs(matches_only=True), read.cigarstring, read.is_reverse, flip(read.get_aligned_pairs(matches_only=True), read.infer_query_length())])
                        else: SA_info[read.query_name].append([read.reference_name, read.infer_query_length(), read.get_aligned_pairs(matches_only=True), read.cigarstring, read.is_reverse, read.get_aligned_pairs(matches_only=True)])
            else: 
                all_aligned[read.reference_name][read.query_name].append(len(read.get_aligned_pairs(matches_only=True))/read.infer_query_length())

####--------------End of stepping through sam/bam file--------------------->>>>>>>>>>>>>>>

####--------------Beg of stepping through reads with supplementary alignments---------------->>>>>>>
    
    #!#!#! Should I add an insertion category? This will likely not be very common with short reads
    fout_del=open("%s_dels_%s.txt" % (outname, opts.orient), 'w')
#    fout_dup=open("%s_dups.txt" % outname, 'w')
    fout_del.write("ReadName\tType\tRefName\tDelLength\tDelLeft\tDelRight\tReadLength\tLeftLen\tRightLen\tOverlap\tOrientation\tStrand\t1stOccurrence?\n")
#    fout_dup.write("ReadName\tType\tRefName\tDupLength\tDupLeft\tDupRight\tReadLength\tLeftLen\tRightLen\tStrand\n")
    
    #Dictionary that will be used to highlight potential PCR duplicates
    uniq_reads = {}
    for k in all_aligned.keys():
        uniq_reads[k]={}
    
    ##Testing: counters/lists to quantify different types of reads with secondary alignments
    
    #Two lists, each will have one entry for each read with more than two secondary alignments
        #The first will hold the number of alignments
        #The second will specify the % of read bases aligned, in total
    morethantwo=[[],[], [], [], []]
    
    only2=0
    sameref=0
    two_same=0
    two_diff=0
    two_same_full=0
    two_diff_full=0
    
    diffref=0
    diffref_samestrand=0
    diffref_diffstrand=0
    diffref_samestrand_full=0
    diffref_diffstrand_full=0

    #These lists will hold info about the % of the read that was aligned to the reference
    two_same_partial=[]
    two_diff_partial=[]
    diffref_samestrand_partial=[]
    diffref_diffstrand_partial=[]

    #These lists will hold info about references to which reads are mapped
    for_right=[]
    for_wrong=[]
    rev_right=[]
    rev_wrong=[]

    partial_for_right=[]
    partial_for_wrong=[]
    partial_rev_right=[]
    partial_rev_wrong=[]

    #To collect info about overlap sizes
    overlaps = {'drds':[], 'drss':[], 'srds':[], 'srssc':[], 'srssi':[]}


    #Create files to write out info
    SRDS = open("%s_sameref_diffstrand.txt" % (opts.out), "w")


    #Step through each read name with at least one secondary alignment
    for read, info in SA_info.iteritems():
        num_aligns = len([x[0] for x in info])
        num_ref = len(set([x[0] for x in info]))
        num_strand = len(set([x[4] for x in info]))
        qsites_aligned, qwithdups = get_aligned([x[5] for x in info], 0)
        rsites_aligned, rwithdups = get_aligned([x[2] for x in info], 1)
        percQaligned = len(qsites_aligned)/max([x[1] for x in info])
        
        #Collecting stats on reads with more than 1 SA
        if num_aligns>2:
            morethantwo[0].append(num_aligns)
            morethantwo[1].append(percQaligned)
            morethantwo[2].append(len(rsites_aligned)/max([x[1] for x in info]))
            morethantwo[3].append(len(qwithdups)/len(qsites_aligned))
            morethantwo[4].append(len(rwithdups)/len(rsites_aligned))
        
        #Collect stats on reads with only 1 SA
        if num_aligns == 2:
            only2+=1
            #Both mapped to the same reference
            if num_ref == 1:
                sameref+=1
                #Both alignments to the same strand
                if num_strand == 1:
                    two_same+=1
                    if percQaligned >= opts.minPerc: 
                        two_same_full+=1
                        #This category will be further parsed below
                    else:
                        two_same_partial.append(percQaligned)
                        #This category will be further parsed below

                #Alignments to two different strands
                elif num_strand == 2:
                    two_diff+=1
                    SRDS.write("%s\t%s\t%d\t%s\t%s\t%s\t%s\t%.2f\n" % (read, info[0][0], info[0][1], info[0][3], info[1][3], str(info[0][4]), str(info[1][4]), percQaligned*100))
                    if percQaligned >= opts.minPerc: 
                        two_diff_full+=1
                        overlaps['srds'].append(len(qwithdups) - len(qsites_aligned))
                    else:
                        two_diff_partial.append(percQaligned)
                        

            #Alignemnts to two different references
            elif num_ref ==2:
                diffref+=1
                #Both alignments to the same strand
                if num_strand == 1:
                    diffref_samestrand+=1
                    if percQaligned >= opts.minPerc: 
                        diffref_samestrand_full+=1
                        overlaps['drss'].append(len(qwithdups) - len(qsites_aligned))
                    else:
                        diffref_samestrand_partial.append(percQaligned)
                #Alignments to two different strands
                elif num_strand == 2:
                    diffref_diffstrand+=1
                    if percQaligned >= opts.minPerc: 
                        diffref_diffstrand_full+=1
                        overlaps['drds'].append(len(qwithdups) - len(qsites_aligned))
                    else:
                        diffref_diffstrand_partial.append(percQaligned)

        #Check to make sure that there are only two alignments, that they are mapped to the same strand and that they are both to the same reference and that the minPerc of the read is aligned, when considering both alignments
        if num_aligns == 2 and num_strand == 1 and num_ref == 1 and percQaligned < opts.minPerc:
            ems = end_minus_start(info[0][2], info[1][2])
            if info[0][4]:
#                strand='reverse'
                if ems>1:
#                    orient='correct'
                    partial_rev_right.append(info[0][0])
                else:
                    partial_rev_wrong.append(info[0][0])
#                    orient='inverted'
            else:
#                strand='forward'
                if ems>1:
                    partial_for_right.append(info[0][0])
#                    orient='correct'
                else:
                    partial_for_wrong.append(info[0][0])
#                    orient='inverted'


        #Check to make sure that there are only two alignments, that they are mapped to the same strand and that they are both to the same reference and that the minPerc of the read is aligned, when considering both alignments
        if num_aligns == 2 and num_strand == 1 and num_ref == 1 and percQaligned >= opts.minPerc:
            ems = end_minus_start(info[0][2], info[1][2])
            if info[0][4]:
                strand='reverse'
                if ems>1:
                    orient='correct'
                    rev_right.append(info[0][0])
                    overlaps['srssc'].append(len(qwithdups) - len(qsites_aligned))
                else:
                    rev_wrong.append(info[0][0])
                    orient='inverted'
                    overlaps['srssi'].append(len(qwithdups) - len(qsites_aligned))
#                        print info[0][2][0], info[0][2][-1], info[1][2][0], info[1][2][-1]
            else:
                strand='forward'
                if ems>1:
                    for_right.append(info[0][0])
                    orient='correct'
                    overlaps['srssc'].append(len(qwithdups) - len(qsites_aligned))
                else:
                    for_wrong.append(info[0][0])
                    orient='inverted'
                    overlaps['srssi'].append(len(qwithdups) - len(qsites_aligned))
            missing = missing_bases(info[0][2], info[1][2])


            if missing and orient==opts.orient: 
                delsig = "%d\t%d\t%d\t%d\t%d\t%d\t%d\t%s" % (len(missing), min(missing)+1, max(missing)+1, max([x[1] for x in info]), len(info[0][2]), len(info[1][2]), len(qwithdups) - len(qsites_aligned), orient)
                if delsig in uniq_reads[info[0][0]]: fout_del.write("%s\tDeletion\t%s\t%s\t%s\t0\n" % (read, info[0][0], delsig, strand))
                else:
                    uniq_reads[info[0][0]][delsig]=''
                    fout_del.write("%s\tDeletion\t%s\t%s\t%s\t1\n" % (read, info[0][0], delsig, strand))
                
#            else:
                ####!!!! Not currently using this portion
                ####!!!! Do I need to adjust?!?!?!
#                common = common_bases([x[1] for x in info[0][2]], [x[1] for x in info[1][2]])
#                if common: fout_dup.write("%s\tDuplication\t%s\t%d\t%d\t%d\t%d\t%d\t%d\t%s\n" % (read, info[0][0], len(common), min(common)+1, max(common)+1, max([x[1] for x in info]), len(info[0][2]), len(info[1][2]), strand))
#                else:
                    #Currently printing info for reads where orientation is not correct
#                    f=1
                    #print max([x[1] for x in info]), len(info[0][2]), len(info[1][2])

    fout_del.close()
    fout_dup.close()

    num_aligned = len(all_align_flip)
    single=0
    single_for=0
    single_rev=0
    for read in all_align_flip.values():
        if len(read)==1:
            for ref in read.values():
                if len(ref) == 1:
                    single+=1
                    if ref[0]: single_rev+=1
                    else: single_for+=1
    
        
    
    print "\nTotal_Aligned: %d" % (num_aligned)
    print "\t2Alignments_Full(>%.1f%%_read_aligned): %d (%.2f%%)" % (opts.minPerc*100, diffref_diffstrand_full+diffref_samestrand_full+two_diff_full+two_same_full, (diffref_diffstrand_full+diffref_samestrand_full+two_diff_full+two_same_full)/num_aligned*100)
    print "\tTotal_wSingleAlignment: %d (%.2f%%)" % (single, single/num_aligned*100)
    print "\t\tForwardStrand: %d (%.2f%%)" % (single_for, single_for/single*100)
    print "\t\tReverseStrand: %d (%.2f%%)" % (single_rev, single_rev/single*100)

    for ref, reads in all_aligned.iteritems():
        single_perc_aligned=[]
        for read in reads:
            #Check that there the read has only one alignment, whether to the same ref or different refs
            if len(all_aligned[ref][read]) == 1 and len(all_align_flip[read]) == 1:
                single_perc_aligned.append(all_aligned[ref][read][0])
        print "\t\t%s:" % (ref)
        print "\t\t\tAvg%%_Read_Aligned: %.2f (STD: %.2f)" % (np.mean(single_perc_aligned)*100, np.std(single_perc_aligned)*100)
        print "\t\t\tFull(>%.1f%%_read_aligned): %.2f (%.2f)" % (opts.minPerc*100, len([x for x in single_perc_aligned if x>=opts.minPerc]), len([x for x in single_perc_aligned if x>=opts.minPerc])/len(single_perc_aligned)*100)
        print "\t\t\tPartial: %.2f (%.2f); avg%%aligned: %.2f" % (len([x for x in single_perc_aligned if x<opts.minPerc]), len([x for x in single_perc_aligned if x<opts.minPerc])/len(single_perc_aligned)*100, np.mean([x for x in single_perc_aligned if x<opts.minPerc])*100)


    print "\nTotal_wSecondaryAlignments: %d (%.2f%%)" % (len(SA_info), len(SA_info)/num_aligned*100)
    print "\t>2_Alignments: %d (%.2f%%)" % (len(morethantwo[0]), len(morethantwo[0])/len(SA_info)*100)
    print "\tOnly2_Alignments: %d (%.2f%%)" % (only2, only2/len(SA_info)*100)
    
    print "\t\tDiff_Ref: %d (%.2f%%)" % (diffref, diffref/only2*100)
    if diffref:
        print "\t\t\tDiff_Strand: %d (%.2f%%)" % (diffref_diffstrand, diffref_diffstrand/diffref*100)
        print "\t\t\t\tFull(>%.1f%%_read_aligned): %d (%.2f%%)" % (opts.minPerc*100, diffref_diffstrand_full, diffref_diffstrand_full/diffref_diffstrand*100)
        print "\t\t\t\tPartial: %d (%.2f%%); avg%%aligned: %.2f" % (len(diffref_diffstrand_partial), len(diffref_diffstrand_partial)/diffref_diffstrand*100, np.mean(diffref_diffstrand_partial)*100)

        print "\t\t\tSame_Strand: %d (%.2f%%)" % (diffref_samestrand, diffref_samestrand/diffref*100)
        print "\t\t\t\tFull(>%.1f%%_read_aligned): %d (%.2f%%)" % (opts.minPerc*100, diffref_samestrand_full, diffref_samestrand_full/diffref_samestrand*100)
        print "\t\t\t\tPartial: %d (%.2f%%); avg%%aligned: %.2f" % (len(diffref_samestrand_partial), len(diffref_samestrand_partial)/diffref_samestrand*100, np.mean(diffref_samestrand_partial)*100)


    if sameref:
        print "\t\tSame_Ref: %d (%.2f%%)" % (sameref, sameref/only2*100)
        print "\t\t\tDiff_Strand: %d (%.2f%%)" % (two_diff, two_diff/sameref*100)
        if two_diff:
            print "\t\t\t\tFull(>%.1f%%_read_aligned): %d (%.2f%%)" % (opts.minPerc*100, two_diff_full, two_diff_full/two_diff*100)
            print "\t\t\t\tPartial: %d (%.2f%%); avg%%aligned: %.2f" % (len(two_diff_partial), len(two_diff_partial)/two_diff*100, np.mean(two_diff_partial)*100)

        print "\t\t\tSame_Strand: %d (%.2f%%)" % (two_same, two_same/sameref*100)
        if two_same:
            print "\t\t\t\tFull(>%.1f%%_read_aligned): %d (%.2f%%)" % (opts.minPerc*100, two_same_full, two_same_full/two_same*100)
            if two_same_full:
                print "\t\t\t\t\tCorrectOrientation: %d (%.2f%%)" % (len(for_right)+len(rev_right), (len(for_right)+len(rev_right))/two_same_full*100)
                print "\t\t\t\t\t\tForwardStrand: %d (%.2f%%)" % (len(for_right), len(for_right)/(len(for_right)+len(rev_right))*100)
                for thisr in set(for_right):
                    thisc = for_right.count(thisr)
                    print "\t\t\t\t\t\t\t%s: %d (%.2f%%)" % (thisr, thisc, thisc/len(for_right)*100)
                print "\t\t\t\t\t\tReverseStrand: %d (%.2f%%)" % (len(rev_right), len(rev_right)/(len(for_right)+len(rev_right))*100)
                for thisr in set(rev_right):
                    thisc = rev_right.count(thisr)
                    print "\t\t\t\t\t\t\t%s: %d (%.2f%%)" % (thisr, thisc, thisc/len(rev_right)*100)
                
                print "\t\t\t\t\tWrongOrientation: %d (%.2f%%)" % (len(for_wrong)+len(rev_wrong), (len(for_wrong)+len(rev_wrong))/two_same_full*100)
                if for_wrong or rev_wrong:
                    print "\t\t\t\t\t\tForwardStrand: %d (%.2f%%)" % (len(for_wrong), len(for_wrong)/(len(for_wrong)+len(rev_wrong))*100)
                    for thisr in set(for_wrong):
                        thisc = for_wrong.count(thisr)
                        print "\t\t\t\t\t\t\t%s: %d (%.2f%%)" % (thisr, thisc, thisc/len(for_wrong)*100)
                    print "\t\t\t\t\t\tReverseStrand: %d (%.2f%%)" % (len(rev_wrong), len(rev_wrong)/(len(for_wrong)+len(rev_wrong))*100)
                    for thisr in set(rev_wrong):
                        thisc = rev_wrong.count(thisr)
                        print "\t\t\t\t\t\t\t%s: %d (%.2f%%)" % (thisr, thisc, thisc/len(rev_wrong)*100)
        
            print "\t\t\t\tPartial: %d (%.2f%%); avg%%aligned: %.2f" % (len(two_same_partial), len(two_same_partial)/two_same*100, np.mean(two_same_partial)*100)
            if two_same_partial:
                print "\t\t\t\t\tCorrectOrientation: %d (%.2f%%)" % (len(partial_for_right)+len(partial_rev_right), (len(partial_for_right)+len(partial_rev_right))/len(two_same_partial)*100)
                print "\t\t\t\t\t\tForwardStrand: %d (%.2f%%)" % (len(partial_for_right), len(partial_for_right)/(len(partial_for_right)+len(partial_rev_right))*100)
                for thisr in set(partial_for_right):
                    thisc = partial_for_right.count(thisr)
                    print "\t\t\t\t\t\t\t%s: %d (%.2f%%)" % (thisr, thisc, thisc/len(partial_for_right)*100)
            
                print "\t\t\t\t\t\tReverseStrand: %d (%.2f%%)" % (len(partial_rev_right), len(partial_rev_right)/(len(partial_for_right)+len(partial_rev_right))*100)
                for thisr in set(partial_rev_right):
                    thisc = partial_rev_right.count(thisr)
                    print "\t\t\t\t\t\t\t%s: %d (%.2f%%)" % (thisr, thisc, thisc/len(partial_rev_right)*100)
            
                print "\t\t\t\t\tWrongOrientation: %d (%.2f%%)" % (len(partial_for_wrong)+len(partial_rev_wrong), (len(partial_for_wrong)+len(partial_rev_wrong))/len(two_same_partial)*100)
                if partial_for_wrong or partial_rev_wrong:
                    print "\t\t\t\t\t\tForwardStrand: %d (%.2f%%)" % (len(partial_for_wrong), len(partial_for_wrong)/(len(partial_for_wrong)+len(partial_rev_wrong))*100)
                    for thisr in set(partial_for_wrong):
                        thisc = partial_for_wrong.count(thisr)
                        print "\t\t\t\t\t\t\t%s: %d (%.2f%%)" % (thisr, thisc, thisc/len(partial_for_wrong)*100)
                
                    print "\t\t\t\t\t\tReverseStrand: %d (%.2f%%)" % (len(partial_rev_wrong), len(partial_rev_wrong)/(len(partial_for_wrong)+len(partial_rev_wrong))*100)
                    for thisr in set(partial_rev_wrong):
                        thisc = partial_rev_wrong.count(thisr)
                        print "\t\t\t\t\t\t\t%s: %d (%.2f%%)" % (thisr, thisc, thisc/len(partial_rev_wrong)*100)

    print "\n"

    print "Overlaps:"
    print "\tChiType\tAvgOvlp\tStdOvlp\t%%WithOvlp\tAvgOvlp-Ovlponly\tStdOvlp-Ovlponly"
    for k in sorted(overlaps.keys()):
        ovlponly = [x for x in overlaps[k] if x>0]
        print "\t%s\t%.3f\t%.3f\t%.2f\t%.3f\t%.3f" % (k, np.mean(overlaps[k]), np.std(overlaps[k]), len(ovlponly)/len(overlaps[k])*100, np.mean(ovlponly), np.std(ovlponly))

#    print "Total_wSecondary\tPercSecondary\tTotalAligned"
#    print len(SA_info), len(SA_info)/num_aligned*100, num_aligned

#    print "2 Alignments only:"
#    print "SameRef (SR)\tSR SameStrand (SS)\tSR DiffStrand (DS)\tSRSS-Full\tSRSS-Partial\tSRDS-Full\tSRDS-Partial\tDiffRef (DR)\tDR-Full\tDR-Partial"
#    print "\t".join([str(x) for x in [sameref, two_same, two_diff, two_same_full, len(two_same_partial), two_diff_full, len(two_diff_partial), diffref, diffref_diffstrand_full+diffref_samestrand_full, len(diffref_diffstrand_partial)+len(diffref_samestrand_partial)]])

#    print len(for_right), len(for_wrong), len(rev_right), len(rev_wrong)
#    print "#MoreThanTwo\tAvg#\t#Std\tAvgPercAligned\tPercStd\tRefAvgPercAligned\tRefPercStd\tAvgPercOvlp\tPercStdOvlp\tRefAvgPercOvlp\tRefPercStdOvlp"
#    print "%d\t%.3f\t%.3f\t%.3f\t%.3f\t%.3f\t%.3f\t%.3f\t%.3f\t%.3f\t%.3f" % (len(morethantwo[0]), np.mean(morethantwo[0]), np.std(morethantwo[0]), np.mean(morethantwo[1]), np.std(morethantwo[1]), np.mean(morethantwo[2]), np.std(morethantwo[2]), np.mean(morethantwo[3]), np.std(morethantwo[3]), np.mean(morethantwo[4]), np.std(morethantwo[4]))

    #Make plots for deletions
    del_info = make_plots("%s_dels.txt" % outname, reflen_dict, opts)
    #Write out info about deletions
    fout = open("%s_delsinfo.txt" % outname, 'w')
    foutall = open("delsinfo.txt", 'a+')
    #Currently include warnings in header that will be included when filtering putative duplicates
    if opts.filterDups:
        fout.write("Ref\t#UniqueChim\t#ReadsChim (filteredDups)\tAvgReadsPerChim (filteredDups)\tStdReadsPerChim (filteredDups)\tMappedReads (not filtered!)\tPropMappedChim (filteredDups, only for chimeric reads)\n")
        foutall.write("Ref\t#UniqueChim\t#ReadsChim (filteredDups)\tAvgReadsPerChim (filteredDups)\tStdReadsPerChim (filteredDups)\tMappedReads (not filtered!)\tPropMappedChim (filteredDups, only for chimeric reads)\n")
    else:
        fout.write("Ref\t#UniqueChim\t#ReadsChim\tAvgReadsPerChim\tStdReadsPerChim\tMappedReads\tPropMappedChim\n")
        foutall.write("Ref\t#UniqueChim\t#ReadsChim\tAvgReadsPerChim\tStdReadsPerChim\tMappedReads\tPropMappedChim\n")
    for ref, info in del_info.iteritems():
        fout.write("%s\t%d\t%d\t%.4f\t%.4f\t%d\t%.4f\n" % (ref, len(info.keys()), sum(info.values()), np.mean(info.values()), np.std(info.values()), len(all_aligned[ref]), sum(info.values())/len(all_aligned[ref])))
        foutall.write("%s\t%s\t%d\t%d\t%.4f\t%.4f\t%d\t%.4f\n" % (bamname, ref, len(info.keys()), sum(info.values()), np.mean(info.values()), np.std(info.values()), len(all_aligned[ref]), sum(info.values())/len(all_aligned[ref])))
    fout.close()
    
    #Still need to work on this part, especially controlling for times when there are few, if any, duplications observed
#    dup_info = make_plots("%s_dups.txt" % outname, opts)


def flip(pairs, length):
    new_pairs=[]
    for q, r in pairs:
        new_pairs.append((length-q-1, r))
    return new_pairs

#!!!To check orientation of alignments
def end_minus_start(pairs1, pairs2):
    #If the first alignment covers an earlier part of the read
    if min([x[0] for x in pairs1]) < min([x[0] for x in pairs2]):
#        print "1st Left"
        max_read_base_ref = [x[1] for x in pairs2][-1]
        min_read_base_ref = [x[1] for x in pairs1][0]
    else:
#        print "1st Right"
        max_read_base_ref = [x[1] for x in pairs1][-1]
        min_read_base_ref = [x[1] for x in pairs2][0]
    return (max_read_base_ref - min_read_base_ref)

def missing_bases(pairs1, pairs2):
    ref1, ref2 = [x[1] for x in pairs1], [x[1] for x in pairs2]
    full=range(min(ref1+ref2), max(ref1+ref2)+1)
    covered = get_covered(pairs1, pairs2)
    missing = list(set(full).difference(set(covered)))
    #Added this section to remove any "missing bases" to the right of the right most mapped base.
    #This is an issue for inverted alignments with multiply mapped bases
    missing_inside = []
    for each in missing:
        if each < max(covered): missing_inside.append(each)
#        else: print each, min(covered), max(covered)
    return missing_inside

#Currently using this to correct for query bases that are multiply mapped to the reference
#Only the left most mapping is included in the output
def get_covered(pairs1, pairs2):
    overlap = set([x[0] for x in pairs1]).intersection(set([x[0] for x in pairs2]))
    if overlap:
        d1 = dict(pairs1)
        d2 = dict(pairs2)
        for q, r in d2.iteritems():
            if q not in d1: d1[q]=r
            elif r<d1[q]: d1[q]=r
        return sorted(d1.values())

    else: return sorted(list(set([x[1] for x in pairs1]+[x[1] for x in pairs2])))

def common_bases(cov1, cov2):
    return list(set(cov1).intersection(set(cov2)))


def corr_hardclipped(read):
    length = read.infer_query_length()
    for t, l in read.cigartuples:
        if t==5: length+=l
    pairs = read.get_aligned_pairs(matches_only=True)
    if read.cigartuples[0][0]==5:
        corr_pairs=[]
        for q, r in pairs:
            corr_pairs.append((q+read.cigartuples[0][1],r))
        return corr_pairs, length
    return pairs,length

def get_aligned(tups, index):
    combo=[]
    for each in tups:
        combo+=[x[index] for x in each]
    return list(set(combo)), combo


###---For plotting

def make_plots(info_file, reflen_dict, opts):
    
    plot_info = {}

# Parse info from file
    linecount=0
    for line in open(info_file, 'r'):
        linecount+=1
        if linecount>1:
            cols = line.strip().split('\t')
            #Check to see if reference name is already a key in the dictionary
            if cols[2] not in plot_info: plot_info[cols[2]]={}
            
            #If filterDups flag is used, a read will only be counted if it is the first occurence
            if not opts.filterDups or int(cols[11]):
                #Check to see if the exact same deletion is already a key in a sub-dictionary, add a count
                if (cols[4],cols[5]) not in plot_info[cols[2]]: plot_info[cols[2]][(cols[4],cols[5])]=1
                else: plot_info[cols[2]][(cols[4],cols[5])]+=1

    for ref, counts in plot_info.iteritems():
        freq_plot(ref, counts, info_file, reflen_dict[ref], opts)
    
    #Return info dict
    return plot_info

def freq_plot(ref, counts, infofile, reflen, opts):

    #Prep data for plot
    start = []
    stop = []
    freq = []

    uniq=0
    for pos, f in counts.iteritems():
        uniq+=1
        start.append(int(pos[0]))
        stop.append(int(pos[1]))
        freq.append(f)

    #To color points by density
    xy = np.vstack([stop,start])
#    print xy
    if uniq>5:
        z = gaussian_kde(xy)(xy)
        #Sort the points by density so that the densest points are plotted last
        idx = z.argsort()
        stop, start, freq, z = np.asarray(stop)[idx], np.asarray(start)[idx], np.asarray(freq)[idx], z[idx]
    else:
        freq = np.asarray(freq)
        z=[1]*uniq


    fig, ax = plt.subplots()
    cax = ax.scatter(stop, start, s=freq*10, c=z, alpha=0.5)
    if uniq>5:
        cbar = fig.colorbar(cax, ticks=[min(z), (min(z)+max(z))/2, max(z)])
        cbar.ax.set_yticklabels(['Low', 'Medium', 'High'])
#    else: cax = ax.scatter(stop, start, s=freq*10, alpha=0.5)
#    lgnd = fig.legend(handles = [cax], labels = ['test'], loc="upper left", scatterpoints=2, columnspacing=20)
    
    ax.set_xlabel('End')
    ax.set_ylabel('Start')
#    ax1.axhline(y=0, xmin=0, xmax=10000, color='k')
    ax.plot([0, reflen], [0, reflen], ls='--', c='0.3')
    ax.set_xlim([0,reflen])
    ax.set_ylim([0,reflen])
    ## plot where the genes are
#    if opts.orfs:
#        for x,i in enumerate(opts.orfs):
#            w=10
#            y=100 + i[-1] * w 
##            print i[0],y,i[1]-i[0]
#            #print (i[1]-i[0])%3,i[2]
#            ax1.arrow(i[0],y,i[1]-i[0],0.0,alpha=0.4,head_width=w,width=w,head_length=0,length_includes_head=True,facecolor='gray',edgecolor='k',zorder=1)
#            ax1.text(np.mean([i[1],i[0]]),y,'%s'%(i[2]),va='center',ha='center',size=10,zorder=2)
#    ax1.set_xticks(x)
#    ax1.set_xticklabels(names)

#For legend
    gll = plt.scatter([],[], s=1*10, marker='o', color='#555555', alpha=0.5)
    gl = plt.scatter([],[], s=mid4leg(max(freq))*10, marker='o', color='#555555', alpha=0.5)
    ga = plt.scatter([],[], s=max(freq)*10, marker='o', color='#555555', alpha=0.5)

    fig.legend((gll,gl,ga), (str(1), "%.0f" % mid4leg(max(freq)), str(max(freq))), scatterpoints=1,
       loc=(0.15, 0.70), ncol=1, fontsize=8, labelspacing=2)
    fig.savefig("%s-%s_freqs.pdf" % (infofile, ref))
    fig.clf()

def mid4leg(maxfreq):
    if maxfreq%2==0: return maxfreq/2
    else: return (maxfreq+1)/2



###---May not be using below this

# will cut fasta name off at the first whitespace
def read_fasta_lists_simple_names(file):
    fin = open(file, 'r')
    count=0

    names=[]
    seqs=[]
    seq=''
    for line in fin:
        line=line.strip()
        if line and line[0] == '>':                #indicates the name of the sequence
            count+=1
            names.append(line[1:].split()[0])
            if count>1:
                seqs.append(seq)
            seq=''
        else: seq +=line
    seqs.append(seq)

    return names, seqs


#writes a new fasta file
def write_fasta(names, seqs, new_filename):
    fout=open(new_filename, 'w')
    for i in range(len(names)):
        fout.write(">%s\n%s\n" % (names[i], seqs[i]))
    fout.close()

def read_fasta_dict_simple_names(file):
    names, seqs = read_fasta_lists_simple_names(file)
    fasta_dict = dict(zip(names, seqs))
    return fasta_dict

###------------END of functions used in building new consensus from pileup----------------------------


        
        
###------------->>>

if __name__ == "__main__":
    main()

