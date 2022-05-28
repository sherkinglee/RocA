#!/usr/bin/env python
# -*- coding:UTF-8 -*-
'''
Author: Li Fajin
Date: 2020-12-23 11:25:23
LastEditors: Li Fajin
LastEditTime: 2021-01-30 19:48:28
Description: This script used for statistics of ribosome profiles on positions around poly-purine sequence moitfs such as AGAG/AGAGA/AGAGAG
'''

import re
import sys
import pysam
import numpy as np
import pandas as pd
from itertools import groupby,chain
from collections import defaultdict
from optparse import OptionParser


def create_parser_for_poly_purine_density():
	'''argument parser.'''
	usage="usage: python %prog [options]"
	parser=OptionParser(usage=usage)
	parser.add_option("-f","--bamListFile",action="store",type="string",default=None,dest="bamListFile",
			help="Bam file list, containing 4 columns.Namely bamFiles,readLength, offSet, bamLegend. '-f' and '-i, -r, -s, -t' parameters are mutually exclusive.default=%default.")
	parser.add_option("-i","--input", action="store",type="string",default=None,dest="bam_files",
			help="Input file(s) in bam format. All files should be split by comma e.g. 1.bam,2.bam,3.bam[required]. '-i' and '-f' are mutually exclusive. default=%default")
	parser.add_option("-c","--coordinateFile",action="store",type="string",dest="coorFile",
			help="The file should contain the coordinate of start and stop codon. Generated by OutputTranscriptInfo.py.[required]")
	parser.add_option("-o","--otput_prefix",action="store",type="string",dest="output_prefix",
			help="Prefix of output files.[required]")
	parser.add_option("-r","--specific_reads_length",action="store",type="string",dest="read_length",
			help="Specific the lenght to do analysis, comma split. e.g. '28,29,30'.If use all length set 'All'. Bam files diff length select split by '_' e.g. '28,29,30_ALL_27,28' [required]. '-r' and '-f' are mutually exclusive.")
	parser.add_option("-s","--offset",action="store",type="string",dest="read_offset",
			help="Specific the offset corresponding to read length, comma split. e.g. '12,13,13'. No offset set 0. Bam files diff offset select split by '_' e.g. '12,13,13_0_12,12' [required]. '-s' and '-f' are mutually exclusive.")
	parser.add_option("-t","--bam_file_legend",action="store",type="string",dest="bam_file_legend",
			help="The legend of each bam files, comma split. e.g. 'condition1,condition2,condition3' [required]. '-t' and '-f' are mutually exclusive.")
	parser.add_option("-M","--filter_mode",action="store",type="string",dest="mode",default='counts',
			help="Mode for filtering transcripts. Either 'counts' or 'RPKM'. default=%default.")
	parser.add_option("-u","--upstream_codon",action="store",type="int",default=0,dest="upstream_codon",
			help="Upstream codon corresponding to start codon (codon unit). While corresponding to stop codon, it is the downstream codon.")
	parser.add_option("-d","--downstream_codon",action="store",type="int",default=500, dest="downstream_codon",
			help="Downstream codon corresponding to start codon (codon unit). While corresponding to stop codon, it is the upstream codon.")
	parser.add_option('-S','--select_trans_list',action="store",type='string',dest='in_selectTrans',
			help="Selected transcript list used for metagene analysis.This files requires the first column must be the transcript ID  with a column name.")
	parser.add_option("-l","--minimum_cds_codon",action="store",type="int",default=150,dest="min_cds_codon",
			help="Minimum CDS codon (codon unit). CDS codons smaller than \"minimum_cds_codon\" will be skipped. default=%default")
	parser.add_option("-n","--minimum_cds_counts",action="store",type="int",default=64,dest="min_cds_counts",
			help="Minimum CDS counts. CDS counts smaller than \"min_cds_counts\" will be skipped. default=%default")
	parser.add_option("-F","--transcript_fasta",action="store",type="string",dest="transcript_fasta",
			help="Input the transcript fasta file used for motif detection and codon density calculation. transcript sequences related with coorFile (longest.trans.info.txt) generated by GetProteinSequence.py")
	parser.add_option('--id-type',action="store",type="string",dest="id_type",default="transcript_id",
			help="define the id type users input. the default is transcript id, if not, will be transformed into transcript id. default=%default")
	parser.add_option('--kmer',action="store",type="int",dest="kmer",default=4,
			help="Length of kmer used for statistics. default=%default")
	parser.add_option("--type",action='store',type='string',dest='Type',default='CDS',help='Type of counts statistics.[CDS/cds or 5UTR/5utr].default=%default')
	parser.add_option("--base",action='store',type='string',dest='base',default='AG',help='Poly base. If AG, output poly-purine.default=%default')


	return parser


class bam_file_attr(object):
	"""Class for bam file attribute"""
	def __init__(self,bamName,bamLen,bamOffset,bamLegend):
		self.bamName=bamName
		self.bamLen=bamLen
		self.bamOffset=bamOffset
		self.bamLegend=bamLegend

def parse_bamListFile(bamListFile):
	bamFileList=[]
	readLengthsList=[]
	OffsetsList=[]
	bamLegendsList=[]
	flag=1
	with open(bamListFile,'r') as f:
		for line in f:
			if flag == 1:
				flag+=1
				continue
			bamFile=line.strip().split("\t")[0]
			readLengths=line.strip().split("\t")[1]
			Offsets=line.strip().split("\t")[2]
			bamLegends=line.strip().split("\t")[3]
			bamFileList.append(bamFile)
			readLengthsList.append(readLengths)
			OffsetsList.append(Offsets)
			bamLegendsList.append(bamLegends)
	return bamFileList,readLengthsList,OffsetsList,bamLegendsList


def fastaIter(transcriptFile):
	'''
	This function is used to get a dict of transcript sequence
	'''
	fastaDict={}
	f=open(transcriptFile,'r')
	faiter=(x[1] for x in groupby(f,lambda line: line.strip()[0]==">")) ## groupby returns a tuple (key, group)
	for header in faiter:
		geneName=header.__next__().strip(">").split(" ")[0]
		seq=''.join(s.strip() for s in faiter.__next__())
		flag=0
		for nt in ['I','K','M','R','S','W','Y','B','D','H','V','N','X']:
			if nt in seq:
				flag+=1
				flag_nt=nt
		if flag != 0:
			print(geneName+" filtered"+"--"+"There is a ambiguous nucleotide",flag_nt,"in your sequence")
			continue
		fastaDict[geneName]=seq
	return fastaDict

def lengths_offsets_split(value):
		''' Split the given comma separated values to multiple integer values'''
		values=[]
		for item in value.split(','):
				item=int(item)
				values.append(item)
		return values

def reload_transcripts_information(longestTransFile):
	selectTrans=set()
	transLengthDict={}
	cdsLengthDict={}
	startCodonCoorDict={}
	stopCodonCoorDict={}
	transID2geneID={}
	transID2geneName={}
	transID2ChromDict={}
	with open(longestTransFile,'r') as f:
		for line in f:
			if line.strip()=='':
				continue
			if line.strip().split("\t")[0] == 'chrom':
				continue
			chrom=line.strip().split("\t")[0]
			transID=line.strip().split("\t")[1]
			geneID=line.strip().split("\t")[3]
			geneName=line.strip().split("\t")[4]
			startCodon=int(line.strip().split("\t")[8])
			stopCodon=int(line.strip().split("\t")[9])
			cds_length=int(line.strip().split("\t")[10])
			transLength=int(line.strip().split("\t")[13])
			selectTrans.add(transID)
			transLengthDict[transID]=transLength
			startCodonCoorDict[transID]=startCodon
			stopCodonCoorDict[transID]=stopCodon
			transID2geneID[transID]=geneID
			transID2geneName[transID]=geneName
			cdsLengthDict[transID]=cds_length
			transID2ChromDict[transID]=chrom
			# print(transID,geneID,geneName,startCodon,stopCodon,transLength)
	print(str(len(selectTrans))+'  transcripts will be used in the follow analysis.\n', file=sys.stderr)
	return selectTrans,transLengthDict,startCodonCoorDict,stopCodonCoorDict,transID2geneID,transID2geneName,cdsLengthDict,transID2ChromDict

def get_trans_frame_counts(ribo_fileobj, transcript_name, read_lengths, read_offsets, transLength, startCoor, stopCoor):
	"""For each mapped read of the given transcript in the BAM file,get the P-site and codon unit reads density
	ribo_fileobj -- file object - BAM file opened using pysam AlignmentFile
	transcript_name -- Name of transcript to get counts for
	read_length -- If provided, get counts only for reads of this length.
	read_offsets -- the offset length corresponding to 5' mapped position.
	transLength -- the length of the transcript.
	startCoor -- the coordinate of the first base of start codon 0-based.
	stopCoor -- the coordinate of the first base of stop codon 0-based.
	"""
	read_counts = np.zeros(transLength,dtype="int64")
	total_reads = 0
	if read_lengths == "ALL" : ## RNA
		for record in ribo_fileobj.fetch(transcript_name):
			if record.flag == 16 or record.flag == 272:
				continue
			total_reads += 1
			position = record.pos
			read_counts[position]+=1
	else:
		read_lengths=lengths_offsets_split(read_lengths)
		read_offsets=lengths_offsets_split(read_offsets)
		for record in ribo_fileobj.fetch(transcript_name):
			if record.flag == 16 or record.flag == 272:
				continue
			for R_length, R_offset in zip(read_lengths,read_offsets):
				if  record.query_length == R_length :
					# if an offset is specified, increment position by that offset.
					position = record.pos + R_offset ## transform into the position of P-site
				else:
					# ignore other reads/lengths
					continue
				total_reads += 1
				try:
					read_counts[position]+=1
				except KeyError:
					print("Dont has this position after offset : transcript_name -> position"+" "+transcript_name+" -> "+position)
	#get trans counts for each 3 frames
	read_counts_frame0=read_counts[(startCoor+0):(stopCoor-2):3]
	read_counts_frame1=read_counts[(startCoor+1):(stopCoor-1):3]
	read_counts_frame2=read_counts[(startCoor+2):(stopCoor-0):3]
	read_counts_frameSum=read_counts_frame0+read_counts_frame1+read_counts_frame2
	cds_reads=sum(read_counts_frameSum)
	return read_counts,read_counts_frameSum,total_reads,cds_reads

def ReshapeVector(trans_vector,pos,upstream,downstream,leftCoor):

	if pos <= upstream:
		tmp_trans_vector_L=trans_vector[:pos]
		tmp=np.zeros(upstream-len(tmp_trans_vector_L),dtype="float")
		tmp_trans_vector_L=np.concatenate((tmp,tmp_trans_vector_L))
		# print(len(tmp_trans_vector_L))
	else:
		tmp_trans_vector_L=trans_vector[(pos-upstream):pos]
		# print(len(tmp_trans_vector_L))

	if leftCoor-pos <=downstream+1:
		tmp_trans_vector_R=trans_vector[pos:(pos+downstream)]
		tmp=np.zeros(downstream+1-len(tmp_trans_vector_R),dtype="float")
		tmp_trans_vector_R=np.concatenate((tmp_trans_vector_R,tmp))
		# print(len(tmp_trans_vector_R))
	else:
		tmp_trans_vector_R=trans_vector[pos:(pos+downstream+1)]
		# print(len(tmp_trans_vector_R))

	tmp_trans_vector=np.concatenate((tmp_trans_vector_L,tmp_trans_vector_R))
	# print(len(tmp_trans_vector))
	return tmp_trans_vector

def StatisticsPolyPurine(in_bamFile,in_selectTrans,in_transcript_sequence,in_transLengthDict,in_startCodonCoorDict,in_stopCodonCoorDict,in_readLengths,in_readOffset,inCDS_countsFilterParma,inCDS_lengthFilterParma,upstream,downstream,mode,Type,kmer,Base,output):
	'''
	statistics of ribosome density on polypurine motifs.
	'''
	filter_1=0
	filter_2=0
	filter_3=0
	filter_4=0
	all_counts=0
	passTransSet=set()
	tmp_trans_vector=np.zeros(upstream+downstream+1,dtype="float")
	fout=open(output,'w')

	## read sam files
	pysamFile=pysam.AlignmentFile(in_bamFile,"rb")
	pysamFile_trans=pysamFile.references
	in_selectTrans=set(pysamFile_trans).intersection(in_selectTrans)
	in_selectTrans=in_selectTrans.intersection(in_transcript_sequence.keys()).intersection(in_startCodonCoorDict.keys())

	for trans in in_startCodonCoorDict.keys():
		leftCoor =int(in_startCodonCoorDict[trans])-1
		rightCoor=int(in_stopCodonCoorDict[trans])-3
		(trans_counts,read_counts_frameSum,total_reads,cds_reads)=get_trans_frame_counts(pysamFile, trans, in_readLengths, in_readOffset, in_transLengthDict[trans], leftCoor, rightCoor)
		all_counts+=total_reads

	for trans in in_selectTrans:
		leftCoor =int(in_startCodonCoorDict[trans])-1 #the first base of start codon 0-base
		rightCoor=int(in_stopCodonCoorDict[trans])-3 #the first base of stop codon 0-base
		trans_seq=in_transcript_sequence[trans]
		cds_seq=trans_seq[leftCoor:(rightCoor+3)]

		if len(cds_seq) % 3 !=0:
			filter_1+=1
			continue
		if len(cds_seq) < inCDS_lengthFilterParma:
			filter_2+=1

		## read counts
		(read_counts,read_counts_frameSum,trans_reads,cds_reads)=get_trans_frame_counts(pysamFile, trans, in_readLengths, in_readOffset, in_transLengthDict[trans], leftCoor, rightCoor)

		trans_reads_normed=np.array(10**6*(read_counts/all_counts))
		trans_reads_mean=np.mean(trans_reads_normed)
		if trans_reads_mean==0:
			continue
		trans_reads_normed=trans_reads_normed/trans_reads_mean
		cds_reads_normed=trans_reads_normed[leftCoor:(rightCoor+3)]
		cds_reads_normed_all=10**9*(cds_reads/(all_counts*len(trans_reads_normed)))

		if mode == "RPKM":
			if cds_reads_normed_all < inCDS_countsFilterParma:
				filter_3+=1
				continue
		if mode == 'counts':
			if cds_reads < inCDS_countsFilterParma:
				filter_3+=1
				continue

		if len(trans_seq)<(upstream+downstream+1):
			filter_4+=1
			continue

		if Type.strip()=="CDS":
			for i in range(leftCoor+upstream,rightCoor+3-downstream): ## change the region as you wish
			# for i in range(leftCoor+upstream,leftCoor+150*3): ## change the region as you wish, -l 450
				motif=trans_seq[i:(i+kmer)]
				if all([base in list(Base) for base in list(motif)]):
					# print(trans,leftCoor,i)
					if len(trans_reads_normed[i-upstream:i+downstream+1])<upstream+downstream+1:
						continue
					region_counts=sum(read_counts[i-upstream:i+downstream+1])
					if region_counts < 16:
						continue
					tmp=tmp_trans_vector+trans_reads_normed[i-upstream:i+downstream+1]
					tmp=[trans,motif,i,i+kmer]+list(tmp)
					fout.write("\t".join(str(i) for i in tmp))
					fout.write("\n")
				else:
					continue
		elif Type.strip()=="5UTR":
			if leftCoor <= kmer or leftCoor<= downstream or leftCoor <= upstream:
				continue
			else:
				for i in range(0+upstream,leftCoor-downstream):
					motif=trans_seq[i:(i+kmer)]
					if all([base in list(Base) for base in list(motif)]):
						region_counts=sum(ReshapeVector(read_counts,i,upstream,downstream,leftCoor))
						if region_counts < 16:
							continue
						tmp=ReshapeVector(trans_reads_normed,i,upstream,downstream,leftCoor)
						print(trans,len(tmp))
						tmp=[trans,motif,i,i+kmer]+list(tmp)
						fout.write("\t".join(str(i) for i in tmp))
						fout.write("\n")
		passTransSet.add(trans)

	pysamFile.close()
	print("The number of genes whose length of CDS could not divided by three: " + str(filter_1),file=sys.stderr)
	print("The number of genes whose length of CDS is less than the criteria: " + str(filter_2),file=sys.stderr)
	print("The number of genes whose read counts on CDS are less than the criteria: " + str(filter_3),file=sys.stderr)
	print("The number of genes whose length < upstream+downstream+1: "+str(filter_4),file=sys.stderr)
	print("The final number of genes used for following analysis is: " + str(len(passTransSet)),file=sys.stderr)


def parse_args_for_poly_purine_density():
	parsed=create_parser_for_poly_purine_density()
	(options,args)=parsed.parse_args()
	if options.bamListFile and (options.bam_files or options.read_length or options.read_offset or options.bam_file_legend):
		raise IOError("'-f' parameter and '-i -r -s -t' are mutually exclusive.")
	if options.bamListFile:
		bamFiles,readLengths,Offsets,bamLegends=parse_bamListFile(options.bamListFile)
	elif options.bam_files:
		bamFiles,readLengths,Offsets,bamLegends=options.bam_files.split(","),options.read_length.split("_"),options.read_offset.split("_"),options.bam_file_legend.split(",")
	else:
		raise IOError("Please check you input files!")
	print("your input : "+ str(len(bamFiles))+" bam files",file=sys.stderr)
	bam_attr=[]
	for ii,jj,mm,nn in zip(bamFiles,readLengths,Offsets,bamLegends):
		bam=bam_file_attr(ii,jj,mm,nn)
		bam_attr.append(bam)
	selectTrans,transLengthDict,startCodonCoorDict,stopCodonCoorDict,transID2geneID,transID2geneName,cdsLengthDict,transID2ChromDict=reload_transcripts_information(options.coorFile)
	geneID2transID={v:k for k,v in transID2geneID.items()}
	geneName2transID={v:k for k,v in transID2geneName.items()}
	if options.in_selectTrans:
		select_trans=pd.read_csv(options.in_selectTrans,sep="\t")
		select_trans=set(select_trans.iloc[:,0].values)
		if options.id_type == 'transcript_id':
			select_trans=select_trans.intersection(selectTrans)
			print("There are " + str(len(select_trans)) + " transcripts from "+options.in_selectTrans+" used for following analysis.",file=sys.stderr)
		elif options.id_type == 'gene_id':
			tmp=[geneID2transID[gene_id] for gene_id in select_trans if gene_id in geneID2transID]
			select_trans=set(tmp)
			select_trans=select_trans.intersection(selectTrans)
			print("There are " + str(len(select_trans))+" gene id could be transformed into transcript id and used for following analysis.",file=sys.stderr)
		elif options.id_type == 'gene_name' or options.id_type=='gene_symbol':
			tmp=[geneName2transID[gene_name] for gene_name in select_trans if gene_name in geneName2transID]
			select_trans=set(tmp)
			select_trans=select_trans.intersection(selectTrans)
			print("There are " + str(len(select_trans))+" gene symbol could be transformed into transcript id and used for following analysis.",file=sys.stderr)
		else:
			raise IOError("Please input a approproate id_type parameters.[transcript_id/gene_id/gene_name/]")
	else:
		select_trans=selectTrans

	transcript_sequence=fastaIter(options.transcript_fasta)


	for bamfs in bam_attr:
		print("Start analyze the sample: "+str(bamfs.bamName),file=sys.stderr)
		StatisticsPolyPurine(bamfs.bamName,select_trans,transcript_sequence,transLengthDict,startCodonCoorDict,stopCodonCoorDict,bamfs.bamLen,bamfs.bamOffset,
		options.min_cds_counts,options.min_cds_codon,options.upstream_codon,options.downstream_codon,options.mode,options.Type,options.kmer,options.base,options.output_prefix+"_"+bamfs.bamLegend+"_poly"+options.base+"_"+str(options.kmer)+"_mer.txt")

	print("Finish!",file=sys.stderr)



def main():
	"""main program"""
	parse_args_for_poly_purine_density()

if __name__ == "__main__":
		main()













