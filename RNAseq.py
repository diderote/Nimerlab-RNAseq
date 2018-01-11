#!/usr/bin/env python
# coding: utf-8

'''
Nimerlab RNASeq Pipeline v0.2

Copyright © 2018 Daniel L. Karl

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation 
files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, 
modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the 
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE 
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR 
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, 
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

Reads an experimetnal design yaml file (Version 0.2).
Requires a conda environment 'RNAseq' made from environment.yml

To do:
    - set up to use any part as needed (specify sig lists for overlap... etc.)
    - rename GSEA output folders and link to results index.html
    - rMATS
    - scale big wigs by scale factors
    - ICA with chi-square with de groups

'''

import os,re,datetime,glob,pickle,time
from shutil import copy2,copytree,rmtree
import subprocess as sub
import pandas as pd
version=0.2

class Experiment(object):
    '''
    Experiment object for pipeline
    '''
    def __init__(self, scratch, date, name, out_dir, job_folder, qc_folder, 
                  log_file,start,fastq_folder,fastq_start,spike,trimmed,
                  count_matrix,spike_counts,stop,genome,sample_number, 
                  samples, job_id,de_groups,norm,designs, overlaps,
                  tasks_complete,de_results,sig_lists,overlap_results,
                  de_sig_overlap
                 ):
        self.scratch = scratch
        self.date = date
        self.name = name
        self.out_dir =out_dir
        self.job_folder=job_folder
        self.qc_folder=qc_folder
        self.log_file=log_file
        self.start=start
        self.fastq_folder=fastq_folder
        self.fastq_start = fastq_start
        self.spike = spike
        self.trimmed = trimmed
        self.count_matrix = count_matrix
        self.spike_counts = spike_counts
        self.stop = stop
        self.genome = genome
        self.sample_number =sample_number
        self.samples = samples
        self.job_id=job_id
        self.de_groups = de_groups
        self.norm = norm
        self.designs=designs
        self.overlaps = overlaps
        self.tasks_complete=tasks_complete
        self.de_results = de_results
        self.sig_lists=sig_lists
        self.overlap_results=overlap_results
        self.de_sig_overlap = de_sig_overlap

def new_experiment():
    experiment = Experiment(scratch = '',
                            date = '',
                            name = '',
                            out_dir ='',
                            job_folder='',
                            qc_folder='',
                            log_file='',
                            start='',
                            fastq_folder='',
                            fastq_start = False,
                            spike = False,
                            trimmed = False,
                            count_matrix = pd.DataFrame(),
                            spike_counts = pd.DataFrame(),
                            stop = '',
                            genome = '',
                            sample_number = {},
                            samples={},
                            job_id=[],
                            de_groups = {},
                            norm = 'bioinformatic',
                            designs={},
                            overlaps = {},
                            tasks_complete=[],
                            de_results = {},
                            sig_lists={},
                            overlap_results={},
                            de_sig_overlap = {}
                           )
    return experiment

class RaiseError(Exception):
    pass

def parse_yaml():
    '''
    Parse experimental info from yaml file
    '''    
    import argparse,yaml
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--experimental_file', '-f', required=True, help='experimental yaml file', type=str)
    args = parser.parse_args()
    exp_input = open(args.experimental_file,'r')


    yml=yaml.safe_load(exp_input)
    exp_input.close()

    #Make a new experimental object
    exp = new_experiment()
    
    #Setting Scratch folder
    exp.scratch = '/scratch/projects/nimerlab/DANIEL/staging/RNAseq/' + yml['Name'] + '/'
    os.makedirs(exp.scratch, exist_ok=True)

    #Passing paramters to new object
    exp.date = datetime.datetime.today().strftime('%Y-%m-%d')   
    exp.name = yml['Name']
    exp.out_dir = yml['Output_directory']
    
    #Make out directory if it doesn't exist
    os.makedirs(exp.out_dir, exist_ok=True)

    #check whether experiment has been attempted
    filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
    
    if os.path.isfile(filename):
        with open(filename, 'rb') as experiment:
            exp = pickle.load(experiment)
        os.remove(filename)

        print('\n#############\nRestarting pipeline on {date}, from last completed step.'.format(date=str(datetime.datetime.now())), file=open(exp.log_file,'a'))

        return exp 
    else: 
        #Setting Job Folder
        exp.job_folder = exp.scratch + 'logs/'
        os.makedirs(exp.job_folder, exist_ok=True)

        #Log file
        exp.log_file = exp.out_dir + exp.name + "-" + exp.date + '.log'
        
        print('Pipeline version ' + str(version) + ' run on ' + exp.date + '\n', file=open(exp.log_file, 'w'))
        print('Beginning RNAseq Analysis: ' + str(datetime.datetime.now()) + '\n', file=open(exp.log_file, 'a'))
        print('Reading experimental file...' + '\n', file=open(exp.log_file, 'a'))

        #Start Point
        start=[]
        if yml['Startpoint']['Fastq']['Start'] : start.append('Fastq') 
        if yml['Startpoint']['Gene_Counts']['Start'] : start.append('Counts')
        if len(start) != 1:
            raise ValueError("There are more than one startpoints in this experimental file.  Please fix the file and resubmit.")
        else:
            exp.start = start[0]
            print('Pipeline starting with: ' + str(exp.start)+ '\n', file=open(exp.log_file, 'a'))

        if exp.start == 'Counts':
            exp.tasks_complete = exp.tasks_complete + ['Fastq_cat','Stage','FastQC','Fastq_screen','Trim','Spike','RSEM','Kallisto','Count_Matrix', 'Sleuth']
       
        #Start Fastq
        if yml['Startpoint']['Fastq']['Start']:
            exp.fastq_start = True
            if yml['Startpoint']['Fastq']['Pre-combined']:
                exp.tasks_complete.append('Fastq_cat')
            if os.path.isdir(yml['Startpoint']['Fastq']['Fastq_directory']):
                exp.fastq_folder=yml['Startpoint']['Fastq']['Fastq_directory']
            else:
                raise IOError("Can't Find Fastq Folder.")

        #Spike
        exp.spike = False
        if yml['ERCC_spike']:
            exp.spike = True

        #Start Gene Counts
        if exp.start == 'Counts':
            if os.path.exists(yml['Startpoint']['Gene_Counts']['Count_matrix_location']):
                exp.count_matrix = pd.read_csv(yml['Startpoint']['Gene_Counts']['Count_matrix_location'], 
                                               header= 0, index_col=0, sep="\t")
            else:
                raise IOError("Count Matrix Not Found.")    
            print("Count matrix found at " + yml['Startpoint']['Gene_Counts']['Count_matrix_location']+ '\n', file=open(exp.log_file, 'a'))
            print("Only performing DESeq2 differential expression.", file=open(exp.log_file, 'a'))
        
        #End Point
        if yml['Stop']['Alignment']:
            exp.stop = 'Alignment'
            exp.tasks_complete = exp.tasks_complete + ['DESeq2','Sleuth','Sigs','Heatmaps','GO_enrich','GSEA_DESeq2','PCA','Overlaps']
            print('Pipeline stopping after alignment.'+ '\n', file=open(exp.log_file, 'a'))
        elif yml['Stop']['Differential_Expression']:
            exp.stop = 'DE'
            exp.tasks_complete = exp.tasks_complete + ['GO_enrich','GSEA_DESeq2','PCA','Overlaps']
            print('Pipeline stopping after differential expression analysis.'+ '\n', file=open(exp.log_file, 'a'))
        else:
            exp.stop = 'END'
            print('Pipeline stopping after full analysis.'+ '\n', file=open(exp.log_file, 'a'))
        
        #Genome
        if yml['Genome'].lower() not in ['hg38', 'mm10']:
            raise ValueError("Genome must be either hg38 or mm10.")
        else:
            exp.genome = yml['Genome'].lower()
            print('Processing data with: ' + str(exp.genome)+ '\n', file=open(exp.log_file, 'a'))
        
        #Counts
        if not 0 < yml['Total_sample_number'] < 19:
            raise ValueError("This pipeline is only set up to handle up to 18 samples.")
        else:
            exp.sample_number = yml['Total_sample_number']
            print('Processing ' + str(exp.sample_number) + ' samples.'+ '\n', file=open(exp.log_file, 'a'))
        
        #Sample Names
        count = 1
        for key,name in yml['Samples'].items():
            if count <= exp.sample_number:
                exp.samples[key]=name
                count += 1
            else:
                break
        print("Samples: "+ '\n', file=open(exp.log_file, 'a'))
        print(str(exp.samples) + '\n', file=open(exp.log_file, 'a'))
        
        #Out Folder
        os.makedirs(exp.out_dir, exist_ok=True)
        print("Pipeline output folder: " + str(exp.out_dir)+ '\n', file=open(exp.log_file, 'a'))
        
        #Differential Expression Groups
        if exp.stop == 'Alignment':
            pass
        else: 
            for key, item in yml['Differential_Expression_Groups'].items():
                if item == None:
                    pass
                else:
                    temp=item.split(',')
                    exp.de_groups[key] = []
                    for x in temp:
                        exp.de_groups[key].append(exp.samples[int(x)])
                
        #Differential Expression Design
        if exp.stop == 'Alignment':
            pass
        else:
            print("Parsing experimental design for differential expression..."+ '\n', file=open(exp.log_file, 'a'))
            
            #Normalization method
            if yml['Differential_Expression_Normalizaiton'] == 'ERCC':
                exp.norm = 'ERCC'
                print('Normalizing samples for differential expression analysis using ERCC spike-ins'+ '\n', file=open(exp.log_file, 'a'))
            elif yml['Differential_Expression_Normalizaiton'] == 'bioinformatic':
                print('Normalizing samples for differential expression analysis using conventional size factors'+ '\n', file=open(exp.log_file, 'a'))
            else:
                print("I don't know the " + yml['Differential_Expression_Normalizaiton'] + ' normalization method.  Using size factors.'+ '\n', file=open(exp.log_file, 'a'))
        
            for key, comparison in yml['Differential_Expression_Comparisons'].items():
                if comparison == None:
                    pass
                else:
                    exp.designs[key]={}
                    E = comparison.split('v')[0]
                    if len(E.split('-')) == 1:
                        E_type = 1
                    elif len(E.split('-')) == 2:
                        E1, E2 = E.split('-')[0], E.split('-')[1]
                        E_type = 2
                    else:
                        raise ValueError("Cannot process " + str(key) + ".  Check format E1 or E1-E2. Or too many Groups for pipline.")
                    C = comparison.split('v')[1]
                    if len(C.split('-')) == 1:
                        C_type = 1
                    elif len(C.split('-'))== 2:
                        C1,C2 = C.split('-')[0], C.split('-')[1]
                        C_type = 2
                    else:
                        raise ValueError("Cannot process " + str(key) + ".  Check format C1 or C1-C2.  Or too man comparisons.")
                
                    #Check comparison for group consistency.
                    error = "Can't make a comparison with an unspecified group. Make sure your Comparisons match your Groups for DE"
                    groups = list(exp.de_groups.keys())
                    
                    exp.designs[key]['all_samples']=[]
                    exp.designs[key]['main_comparison']=[]
                    exp.designs[key]['compensation']=[]
                    
                    if E_type == 1:
                        if E not in groups:
                            raise ValueError(error)
                        else:
                            exp.designs[key]['all_samples'].extend(exp.de_groups[E])
                            exp.designs[key]['main_comparison'].extend(['Experimental']*len(exp.de_groups[E]))
                            if C_type == 1:
                                if C not in groups:
                                    raise ValueError(error)
                                else:
                                    exp.designs[key]['all_samples'].extend(exp.de_groups[C])
                                    exp.designs[key]['main_comparison'].extend(['Control']*len(exp.de_groups[C]))
                            elif C_type == 2:
                                raise ValueError("Cannot batch compensate 1 Experimental group with 2 Control groups")
                            else:
                                raise ValueError(error)
                            
                            exp.designs[key]['design'] = "~main_comparison"
                            exp.designs[key]['colData'] = pd.DataFrame({"sample_names": exp.designs[key]['all_samples'],
                                                                        "main_comparison": exp.designs[key]['main_comparison']})
                        print('DE design: '+ '\n', file=open(exp.log_file, 'a'))
                        print(str(exp.designs) + '\n', file=open(exp.log_file, 'a')) 
                    elif E_type == 2:
                        if E1 not in groups or E2 not in groups:
                            raise ValueError(error)
                        else:
                            exp.designs[key]['all_samples'].extend(exp.de_groups[E1])
                            exp.designs[key]['all_samples'].extend(exp.de_groups[E2])
                            exp.designs[key]['main_comparison'].extend(['Experimental']*len(exp.de_groups[E1] + exp.de_groups[E2]))
                            if C_type == 1:
                                raise ValueError("Cannot batch compensate 2 Experimental groups with 1 Control groups.")
                            elif C_type == 2:
                                if C1 not in groups or C2 not in groups:
                                    raise ValueError(error)
                                else:
                                    exp.designs[key]['all_samples'].extend(exp.de_groups[C1])
                                    exp.designs[key]['all_samples'].extend(exp.de_groups[C2])
                                    exp.designs[key]['main_comparison'].extend(['Control']*len(exp.de_groups[C1] + exp.de_groups[C2]))
                            else:
                                raise ValueError(error)                                     
                            
                            exp.designs[key]['compensation'].extend((['Group_1']*len(exp.de_groups[E1]) +
                                                                     ['Group_2']*len(exp.de_groups[C1]) +
                                                                     ['Group_1']*len(exp.de_groups[E2]) +
                                                                     ['Group_2']*len(exp.de_groups[C2])))
                            exp.designs[key]['design'] = "~compensation + main_comparison"
                            exp.designs[key]['colData']= pd.DataFrame({"sample_names": exp.designs[key]['all_samples'],
                                                                       "main_comparison": exp.designs[key]['main_comparison'],
                                                                       "compensation": exp.designs[key]['compensation']})
                        print('DE design: '+ '\n', file=open(exp.log_file, 'a'))
                        
                        for name,items in exp.designs.items():
                            print('{}:'.format(name), file=open(exp.log_file,'a'))
                            print(str(items['colData']), file=open(exp.log_file,'a'))
                            print('{} design:'.format(name), file=open(exp.log_file, 'a')) 
                            print(str(items['design']), file=open(exp.log_file,'a'))
                    else:
                        raise ValueError(error)

        #Initialize DE sig overlaps
        for comparison, design in exp.designs.items():
            if exp.start == 'Counts':
                exp.de_sig_overlap[comparison] = False
            elif yml['Differential_Expression_Mode'].lower() == 'deseq2':
                exp.de_sig_overlap[comparison] = False
            else:
                exp.de_sig_overlap[comparison] = True
            
        #DE overlaps
        if yml['Overlaps'] == None:
            print('There are no overlaps to process for muliptle differential expression analyses.'+ '\n', file=open(exp.log_file, 'a'))
            exp.run_overlap = False
        else:
            exp.run_overlap = True
            for key, item in yml['Overlaps'].items():
                if item == None:
                    pass    
                else:
                    exp.overlaps[key] = item.split('v')
            print('Overlapping ' + str(len(list(exp.overlaps.keys()))) + ' differential analysis comparison(s).', file=open(exp.log_file, 'a'))
            if str(len(list(exp.overlaps.keys()))) != 0:
                print(str(exp.overlaps)+ '\n', file=open(exp.log_file, 'a'))
            
        #Initialized Process Complete List
        exp.tasks_complete.append('Parsed')

        print('Experiment file parsed: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
        
        return exp

def send_job(command_list, job_name, job_log_folder, q, mem, log_file):
    '''
    Sends job to LSF pegasus.ccs.miami.edu
    '''
    import random
    
    os.makedirs(job_log_folder, exist_ok=True)

    rand_id = str(random.randint(0, 100000))
    str_comd_list =  '\n'.join(command_list)
    cmd = '''
    #!/bin/bash

    #BSUB -J JOB_{job_name}_ID_{random_number}
    #BSUB -P nimerlab
    #BSUB -o {job_log_folder}{job_name_o}_logs_{rand_id}.stdout.%J
    #BSUB -e {job_log_folder}{job_name_e}_logs_{rand_id}.stderr.%J
    #BSUB -W 120:00
    #BSUB -n 1
    #BSUB -q {q}
    #BSUB -R "rusage[mem={mem}]"

    {commands_string_list}'''.format(job_name = job_name,
                                     job_log_folder=job_log_folder,
                                     job_name_o=job_name,
                                     job_name_e=job_name,
                                     commands_string_list=str_comd_list,
                                     random_number=rand_id,
                                     rand_id=rand_id,
                                     q=q,
                                     mem=mem
                                    )
    
    job_path_name = job_log_folder + job_name+'.sh'
    write_job = open(job_path_name, 'w')
    write_job.write(cmd)
    write_job.close()
    os.system('bsub < {}'.format(job_path_name))
    print('sending job ID_{rand_id}...'.format(rand_id=str(rand_id)), file=open(log_file, 'a'))
    time.sleep(1) #too many conda activations at once sometimes leads to inability to activate during a job.
   
    return rand_id

def job_wait(id_list, job_log_folder, log_file):
    '''
    Waits for jobs sent by send job to finish.
    '''
    running = True
    while running:
        jobs_list = os.popen('sleep 60|bhist -w').read()
        current=[]
        for rand_id in id_list:
            if len([j for j in re.findall('ID_(\d+)', jobs_list) if j == rand_id]) != 0:
                current.append(rand_id)
        if len(current) == 0:
            running = False
        else:
            print('Waiting for jobs to finish... {time}'.format(time=str(datetime.datetime.now())), file=open(log_file, 'a'))
    
def fastq_cat(exp):
    '''
    Illumina basespace changed format for fastq downloads.  This def needs to be updated to reflect this.
    '''
    if 'Fastq_cat' in exp.tasks_complete:
        return exp

    else:
        '''
        ### Better way may be to glob all files in fastq subfolders

        files_all = glob.glob(exp.fastq_folder + '**/**/*.gz', recursive=True)
        files = []
        for file in files_all:
            if file in files:
                pass
            else:
                files.append(file)

        os.makedirs(exp.fastq_folder + 'temp/', exist_ok=True)
        for file in files:
            shutil.move(file,exp.fastq_folder + 'temp/')

        for number in exp.sample_number: 
            sample = 'G{num:02d}'.format(num=number + 1)  #PROBLEM IS THAT CORE CONVENTION CHANGES FREQUENTLY
            for R in ['R1','R2']:
                Reads=glob.glob('{loc}*{sample}*_{R}_*.fastq.gz'.format(loc=exp.fastq_folder + 'temp/',sample=sample,R=R))
                command = 'cat '    
                for read in Reads:
                    command = command + read + ' '
                command = command + '> {loc}{sample}_{R}.fastq.gz'.format(loc=exp.fastq_folder,sample=exp.samples[sample_number + 1],R=R)
                os.system(command)
        
        rmtree(exp.fastq_folder + 'temp/')

        exp.tasks_complete.append('Fastq_cat')
        return exp
        '''
        print('Pipeline not set up to handle fastq merging yet.', file=open(exp.log_file,'a'))
        raise RaiseError('Pipeline not set up to handle fastq merging yet.  Use "cat file1 file2 > final_file" to manually merge then restart.')

def stage(exp):
    '''
    Stages files in Pegasus Scratch
    '''
    if 'Stage' in exp.tasks_complete:
        return exp

    else:

        set_temp='/scratch/projects/nimerlab/tmp'
        sub.run('export TMPDIR=' + set_temp, shell=True)
        print('TMP directory set to ' + set_temp+ '\n', file=open(exp.log_file, 'a'))
        
        #Stage Experiment Folder in Scratch
        print('Staging in ' + exp.scratch+ '\n', file=open(exp.log_file, 'a'))
        
        #Copy Fastq to scratch fastq folder
        if os.path.exists(exp.scratch + 'Fastq'):
            rmtree(exp.scratch + 'Fastq')
        copytree(exp.fastq_folder, exp.scratch + 'Fastq')

        #change to experimental directory in scratch
        os.chdir(exp.scratch)
        
        exp.fastq_folder= exp.scratch + 'Fastq/'
        
        exp.tasks_complete.append('Stage')
        
        print('Staging complete: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
        
        return exp

def fastqc(exp):
    '''
    Performs fastq spec analysis with FastQC
    '''
    if 'FastQC' in exp.tasks_complete:
        return exp

    else:
        try:
            print('Assessing fastq quality.'+ '\n', file=open(exp.log_file, 'a'))

            #Make QC folder
            exp.qc_folder = exp.scratch + 'QC/'
            os.makedirs(exp.qc_folder, exist_ok=True)
            
                
            for number,sample in exp.samples.items():
                command_list = ['module rm python',
                                'module rm perl',
                                'source activate RNAseq',
                                'fastqc ' + exp.fastq_folder + sample + '*',
                               ]

                exp.job_id.append(send_job(command_list=command_list, 
                                           job_name= sample + '_fastqc',
                                           job_log_folder=exp.job_folder,
                                           q= 'general',
                                           mem=1000,
                                           log_file=exp.log_file
                                          )
                                 )

            #Wait for jobs to finish
            job_wait(id_list=exp.job_id, job_log_folder=exp.job_folder, log_file=exp.log_file)
            
            #move to qc folder
            fastqc_files = glob.glob(exp.fastq_folder + '*.zip')
            fastqc_files = fastqc_files + glob.glob(exp.fastq_folder + '*.html')
            for f in fastqc_files:
                copy2(f,exp.qc_folder)
                os.remove(f)
             
            exp.tasks_complete.append('FastQC')
            
            print('FastQC complete: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
            
            return exp
        
        except:
            print('Error in FastQC.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error in FastQC. Fix problem then resubmit with same command to continue from last completed step.')

def fastq_screen(exp):
    '''
    Checks fastq files for contamination with alternative genomes using Bowtie2
    '''
    if 'Fastq_screen' in exp.tasks_complete:
        return exp

    else:
        try:

            print('Screening for contamination during sequencing: '  + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
            
            #Make QC folder
            exp.qc_folder = exp.scratch + 'QC/'
            os.makedirs(exp.qc_folder, exist_ok=True)

            #change to experimental directory in scratch
            os.chdir(exp.fastq_folder)
            
            #Submit fastqc and fastq_screen jobs for each sample
            for number,sample in exp.samples.items():
                command_list = ['module rm python',
                                'module rm perl',
                                'source activate RNAseq',
                                'fastq_screen --aligner bowtie2 ' + exp.fastq_folder + sample + '_R1.fastq.gz'
                               ]

                exp.job_id.append(send_job(command_list=command_list, 
                                           job_name= sample + '_fastq_screen',
                                           job_log_folder=exp.job_folder,
                                           q= 'general',
                                           mem=3000,
                                           log_file=exp.log_file
                                          )
                                 )
                time.sleep(1)
            
            #Wait for jobs to finish
            job_wait(id_list=exp.job_id, job_log_folder=exp.job_folder, log_file=exp.log_file)
            
            #move to qc folder        
            fastqs_files = glob.glob(exp.fastq_folder + '*screen*')
            for f in fastqs_files:
                copy2(f,exp.qc_folder)
                os.remove(f)

            #change to experimental directory in scratch
            os.chdir(exp.scratch)
            exp.tasks_complete.append('Fastq_screen')
            print('Screening complete: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
            
            return exp

        except:
            print('Error in Fastq Screen.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error in Fastq_screen. Fix problem then resubmit with same command to continue from last completed step.')


def trim(exp):
    '''
    Trimming based on standard UM SCCC Core Nextseq 500 technical errors.  Cudadapt can hard clip both ends, but may ignore 3' in future.
    '''
    if 'Trim' in exp.tasks_complete:
        exp.trimmed = True
        return exp

    else:
        try:
            print('Beginning fastq trimming: '  + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
                
            #change to experimental directory in scratch
            os.chdir(exp.fastq_folder)
            
            scan=0
            while scan < 2:

                #Submit trimming files for each sample
                for number,sample in exp.samples.items():

                    if '{loc}{sample}_trim_R2.fastq.gz'.format(loc=exp.fastq_folder,sample=sample) in glob.glob(exp.fastq_folder + '*.gz'):
                        pass

                    else:
                        print('Trimming {sample}: '.format(sample=sample)+ '\n', file=open(exp.log_file, 'a'))
                        
                        cutadapt = 'cutadapt -a AGATCGGAAGAGC -A AGATCGGAAGAGC --cores=10 --nextseq-trim=20 -u 2 -u -4 -U 2 -U -4 -m 18 -o {loc}{sample}_trim_R1.fastq.gz -p {loc}{sample}_trim_R2.fastq.gz {loc}{sample}_R1.fastq.gz {loc}{sample}_R2.fastq.gz'.format(qc=exp.qc_folder,loc=exp.fastq_folder,sample=sample)
                        command_list = ['module rm python',
                                        'module rm perl',
                                        'source activate RNAseq',
                                        cutadapt
                                       ]

                        exp.job_id.append(send_job(command_list=command_list, 
                                                   job_name= sample + "_trim",
                                                   job_log_folder=exp.job_folder,
                                                   q= 'general',
                                                   mem=1000,
                                                   log_file=exp.log_file
                                                  )
                                         )
                    
                #Wait for jobs to finish
                job_wait(id_list=exp.job_id, job_log_folder=exp.job_folder, log_file=exp.log_file)

                scan += 1
            
            #move logs to qc folder        
            print('Trimming logs are found in stdout files from bsub.  Cutadapt does not handle log files in multi-core mode.', file=open(exp.log_file, 'a'))

            for number,sample in exp.samples.items():
                if '{loc}{sample}_trim_R2.fastq.gz'.format(loc=exp.fastq_folder,sample=sample) not in glob.glob(exp.fastq_folder + '*.gz'):
                    raise RaiseError('Not all samples were trimmed.')

            #change to experimental directory in scratch
            os.chdir(exp.scratch)

            exp.trimmed = True 
            exp.tasks_complete.append('Trim')
            print('Trimming complete: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))

            return exp

        except:
            print('Error in trimming.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error during trimming. Fix problem then resubmit with same command to continue from last completed step.')

def spike(exp):
    '''
    Align sequencing files to ERCC index using STAR aligner.
    '''
    if 'Spike' in exp.tasks_complete:
        return exp

    elif exp.spike:
        try:
            print("Processing with ERCC spike-in: " + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
                
            ERCC_folder=exp.scratch + 'ERCC/'
            os.makedirs(ERCC_folder, exist_ok=True)

            scan = 0
            while scan < 2:
                for number,sample in exp.samples.items():
                    #Scan if succesful during second loop.
                    if '{loc}{sample}_ERCCReadsPerGene.out.tab'.format(loc=ERCC_folder,sample=sample) in glob.glob(ERCC_folder + '*.tab'):
                        pass

                    else:
                        #Submit STAR alingment for spike-ins for each sample
                        print('Aligning {sample} to spike-in.'.format(sample=sample)+ '\n', file=open(exp.log_file, 'a'))

                        spike='STAR --runThreadN 10 --genomeDir /projects/ctsi/nimerlab/DANIEL/tools/genomes/ERCC_spike/STARIndex --readFilesIn {floc}{sample}_trim_R1.fastq.gz {floc}{sample}_trim_R2.fastq.gz --readFilesCommand zcat --outFileNamePrefix {loc}{sample}_ERCC --quantMode GeneCounts'.format(floc=exp.fastq_folder,loc=ERCC_folder,sample=sample)

                        command_list = ['module rm python',
                                        'module rm perl',
                                        'source activate RNAseq',
                                        spike
                                       ]

                        exp.job_id.append(send_job(command_list=command_list, 
                                                   job_name= sample + '_ERCC',
                                                   job_log_folder=exp.job_folder,
                                                   q= 'general',
                                                   mem=5000,
                                                   log_file=exp.log_file
                                                  )
                                         )

                #Wait for jobs to finish
                job_wait(id_list=exp.job_id, job_log_folder=exp.job_folder, log_file=exp.log_file)

                scan += 1

            print('Spike-in alignment jobs finished.', file=open(exp.log_file, 'a'))
            
            ### Generate one matrix for all spike_counts
            try:
                ERCC_counts = glob.glob(ERCC_folder + '*_ERCCReadsPerGene.out.tab')
                if len(ERCC_counts) != exp.sample_number:
                    print('At least one ERCC alignment failed.', file=open(exp.log_file,'a'))
                    filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
                    with open(filename, 'wb') as experiment:
                        pickle.dump(exp, experiment)
                    raise RaiseError('At least one ERCC alignment failed. Check scripts and resubmit.')
                else:
                    exp.spike_counts = pd.DataFrame(index=pd.read_csv(ERCC_counts[1], header=None, index_col=0, sep="\t").index)
                
                    for number,sample in exp.samples.items():
                        exp.spike_counts[sample] = pd.read_csv('{loc}{sample}_ERCCReadsPerGene.out.tab'.format(loc=ERCC_folder, sample=sample),header=None, index_col=0, sep="\t")[[3]]
                    exp.spike_counts = exp.spike_counts.iloc[4:,:]
                    exp.spike_counts.to_csv('{loc}ERCC.count.matrix'.format(loc=ERCC_folder), header=True, index=True, sep="\t")
            except:
                print('Error generating spike_count matrix.', file=open(exp.log_file,'a'))
                raise RaiseError('Error generating spike_count matrix. Make sure the file is not empty.')
            
            print("ERCC spike-in processing complete: " + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
        
        except:
            print('Error in spike-in processing.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error during ERCC spike-in processing. Fix problem then resubmit with same command to continue from last completed step.')

    else:
        print("No ERCC spike-in processing."+ '\n', file=open(exp.log_file, 'a'))
    
    exp.tasks_complete.append('Spike')
    return exp 

def rsem(exp):
    '''
    Alignment to transcriptome using STAR and estimating expected counts using EM
    '''
    if 'RSEM' in exp.tasks_complete:
        return exp

    else:
        try:    
            print('Beginning RSEM-STAR alignments: '  + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
            
            RSEM_out = exp.scratch + 'RSEM_results/'
            os.makedirs(RSEM_out, exist_ok=True)
            os.chdir(RSEM_out)        

            scan=0
            while scan < 2: #Loop twice to make sure source activate didn't fail the first time
                for number,sample in exp.samples.items():      
                    if '{loc}{sample}.rsem.bw'.format(loc=RSEM_out,sample=sample) in glob.glob(RSEM_out + '*.bw'):
                        pass
                    else:
                        print('Aligning using STAR and counting transcripts using RSEM for {sample}.'.format(sample=sample)+ '\n', file=open(exp.log_file, 'a'))

                        if exp.genome == 'hg38':
                            align='rsem-calculate-expression --star --star-gzipped-read-file --paired-end --append-names --output-genome-bam --sort-bam-by-coordinate -p 15 {loc}{sample}_trim_R1.fastq.gz {loc}{sample}_trim_R2.fastq.gz /projects/ctsi/nimerlab/DANIEL/tools/genomes/H_sapiens/Ensembl/GRCh38/Sequence/RSEM_STARIndex/human {sample}'.format(loc=exp.fastq_folder,sample=sample)
                            wig2bw='wigToBigWig {sample}.wig /projects/ctsi/nimerlab/DANIEL/tools/genomes/H_sapiens/Ensembl/GRCh38/Sequence/RSEM_STARIndex/chrNameLength.txt {sample}.rsem.bw'.format(sample=sample)
                        elif exp.genome == 'mm10':
                            align='rsem-calculate-expression --star --star-gzipped-read-file --paired-end --append-names --output-genome-bam --sort-bam-by-coordinate -p 15 {loc}{sample}_trim_R1.fastq.gz {loc}{sample}_trim_R2.fastq.gz /projects/ctsi/nimerlab/DANIEL/tools/genomes/Mus_musculus/Ensembl/GRCm38/Sequence/RSEM_STARIndex/mouse {sample}'.format(loc=exp.fastq_folder,sample=sample)
                            wig2bw='wigToBigWig {sample}.wig /projects/ctsi/nimerlab/DANIEL/tools/genomes/Mus_musculus/Ensembl/GRCm38/Sequence/RSEM_STARIndex/chrNameLength.txt {sample}.rsem.bw'.format(sample=sample)
                        else:
                            print('Error in star/rsem alignment, cannot align to genome other than mm10 or hg38.', file=open(exp.log_file,'a'))
                            raise IOError('This pipeline only handles mm10 or hg38 genomes.  Please fix and resubmit.')
                         
                        bam2wig='rsem-bam2wig {sample}.genome.sorted.bam {sample}.wig {sample}'.format(sample=sample)
                        plot_model='rsem-plot-model {sample} {sample}.models.pdf' .format(sample=sample)  

                        command_list = ['module rm python',
                                        'module rm perl',
                                        'source activate RNAseq',
                                        align,
                                        bam2wig,
                                        wig2bw,
                                        plot_model
                                        ]

                        exp.job_id.append(send_job(command_list=command_list, 
                                                    job_name= sample + '_RSEM',
                                                    job_log_folder=exp.job_folder,
                                                    q= 'bigmem',
                                                    mem=60000,
                                                    log_file=exp.log_file
                                                    )
                                          )
                        time.sleep(5)

                #Wait for jobs to finish
                job_wait(id_list=exp.job_id, job_log_folder=exp.job_folder, log_file=exp.log_file)
            
                scan += 1

            remove_files = ['genome.bam','transcript.bam','transcript.sorted.bam','transcrpt.sorted.bam.bai','wig']
            for number,sample in exp.samples.items():
                for file in reomve_files:
                    del_file='{RSEM_out}{sample}.{file}'.format(RSEM_out=RSEM_out, sample=sample,file=file)
                    if os.path.isfile(del_file):
                        os.remove(del_file)

            os.chdir(exp.scratch)
            exp.tasks_complete.append('RSEM')
            print('STAR alignemnt and RSEM counts complete: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
            
            return exp
        
        except:
            print('Error during STAR/RSEM alignment.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error during STAR/RSEM alignment. Fix problem then resubmit with same command to continue from last completed step.')

def kallisto(exp):
    '''
    Second/alternate alignment to transcriptome using kallisto
    '''


    if 'Kallisto' in exp.tasks_complete:
        return exp

    else:
        try:
            #make Kallisto_results folder
            os.makedirs(exp.scratch + 'Kallisto_results/', exist_ok=True)

            scan = 0
            while scan < 2:

                print('Beginning Kallisto alignments: '  + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))

                #Submit kallisto for each sample
                for number,sample in exp.samples.items():

                    kal_out = exp.scratch + 'Kallisto_results/' + sample + '/'
                    os.makedirs(kal_out, exist_ok=True)

                    if '{loc}abundance.tsv'.format(loc=kal_out) in glob.glob(kal_out + '*.tsv'):
                        pass 
                    
                    else:   
                        if exp.genome == 'hg38':
                            align = 'kallisto quant --index=/projects/ctsi/nimerlab/DANIEL/tools/genomes/H_sapiens/Ensembl/GRCh38/Sequence/KallistoIndex/GRCh38.transcripts.idx --output-dir={out} --threads=15 --bootstrap-samples=100 {loc}{sample}_trim_R1.fastq.gz {loc}{sample}_trim_R2.fastq.gz'.format(out=kal_out,loc=exp.fastq_folder,sample=sample)
                        elif exp.genome == 'mm10':
                            align='kallisto quant --index=/projects/ctsi/nimerlab/DANIEL/tools/genomes/Mus_musculus/Ensembl/GRCm38/Sequence/KallistoIndex/GRCm38.transcripts.idx --output-dir={out} --threads=15 --bootstrap-samples=100 {loc}{sample}_trim_R1.fastq.gz {loc}{sample}_trim_R2.fastq.gz'.format(out=kal_out,loc=exp.fastq_folder,sample=sample)
                        else:
                            print('Error in kallisto alignment, cannot align to genome other than mm10 or hg38.', file=open(exp.log_file,'a'))
                            raise IOError('This pipeline only handles mm10 or hg38 genomes.  Please fix and resubmit.')

                        print('Aligning {sample} using Kallisto.'.format(sample=sample)+ '\n', file=open(exp.log_file, 'a'))

                        command_list = ['module rm python',
                                        'module rm perl',
                                        'source activate RNAseq',
                                        align
                                       ]

                        exp.job_id.append(send_job(command_list=command_list, 
                                                   job_name= sample + '_Kallisto',
                                                   job_log_folder=exp.job_folder,
                                                   q= 'general',
                                                   mem=10000,
                                                   log_file=exp.log_file
                                                  )
                                         )

                #Wait for jobs to finish
                job_wait(id_list=exp.job_id, job_log_folder=exp.job_folder, log_file=exp.log_file)
                    
                scan += 1

            exp.tasks_complete.append('Kallisto')
            
            return exp

        except:
            print('Error during Kallisto alignment.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error during Kallisto alignment. Fix problem then resubmit with same command to continue from last completed step.')

def count_matrix(exp):
    '''
    Generates Count Matrix from RSEM results.
    '''
    
    if 'Count_Matrix' in exp.tasks_complete:
        return exp

    else:
        try: 

            print('Generating Sample Matrix from RSEM.gene.results: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))

            ### Generate one matrix for all expected_counts
            matrix='rsem-generate-data-matrix '
            columns=[]
            for number,sample in exp.samples.items():
                matrix = matrix + exp.scratch + 'RSEM_results/' + sample + '.genes.results '
                columns.append(sample)
                
            matrix = matrix + '> {loc}RSEM.count.matrix'.format(loc=exp.scratch + 'RSEM_results/')
                
            command_list = ['module rm python',
                            'source activate RNAseq',
                            matrix
                           ]

            exp.job_id.append(send_job(command_list=command_list, 
                                       job_name= 'Generate_Count_Matrix',
                                       job_log_folder=exp.job_folder,
                                       q= 'general',
                                       mem=1000,
                                       log_file=exp.log_file
                                      )
                             )
            
            #Wait for jobs to finish
            job_wait(id_list=exp.job_id, job_log_folder=exp.job_folder, log_file=exp.log_file)
            
            counts = pd.read_csv('{loc}RSEM.count.matrix'.format(loc=(exp.scratch + 'RSEM_results/')), header=0, index_col=0, sep="\t")
            counts.columns = columns
            counts.to_csv('{loc}RSEM.count.matrix'.format(loc=(exp.scratch + 'RSEM_results/')), header=True, index=True, sep="\t")

            exp.count_matrix = counts
            exp.tasks_complete.append('Count_Matrix')
            print('Sample count matrix complete: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
            
            return exp

        except:
            print('Error during RSEM count matrix generation.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error during RSEM count matrix generation. Fix problem then resubmit with same command to continue from last completed step.')
    
def DESeq2(exp):
        
    '''
    Differential Expression using DESeq2
    '''
    
    if 'DESeq2' in exp.tasks_complete:
        print('DESeq2 already finished.', file=open(exp.log_file,'a'))
        return exp

    else:
        try:

            print('Beginning DESeq2 differential expression analysis: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
            
            import numpy as np
            import rpy2.robjects as ro
            from rpy2.robjects.packages import importr
            from rpy2.robjects import pandas2ri
            pandas2ri.activate()
            
            deseq = importr('DESeq2')
            as_df=ro.r("as.data.frame")
            assay=ro.r("assay")
            session=ro.r("sessionInfo")
            
            out_dir= exp.scratch + 'DESeq2_results/'
            os.makedirs(out_dir, exist_ok=True)
            
            count_matrix = exp.count_matrix
            dds={}
            
            for comparison,designs in exp.designs.items():
                print('Beginning ' + comparison + ': ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
                colData=designs['colData']
                design=ro.Formula(designs['design'])
                data=count_matrix[designs['all_samples']]
                data = data[data.sum(axis=1) > 1]
                data = round(data).astype(int)
                dds[comparison] = deseq.DESeqDataSetFromMatrix(countData = data.values,
                                                               colData=colData,
                                                               design=design
                                                              )
                
                dds[comparison] = deseq.DESeq(dds[comparison])
                
                if exp.norm == 'ERCC':
                    print('Determining ERCC size factors...'+ '\n', file=open(exp.log_file, 'a'))
                    ERCC_data = exp.spike_counts[designs['all_samples']]
                    ERCC_dds = deseq.DESeqDataSetFromMatrix(countData = ERCC_data.values, colData=colData, design=design)
                    ERCC_size = deseq.estimateSizeFactors_DESeqDataSet(ERCC_dds)
                    deseq2_size = deseq.estimateSizeFactors_DESeqDataSet(dds[comparison])
                    sizeFactors=ro.r("sizeFactors")
                    dds[comparison].do_slot('colData').do_slot('listData')[1] = sizeFactors(ERCC_size)
                    dds[comparison] = deseq.DESeq(dds[comparison])

                    #compare size factors from DESeq2 and ERCC for inconsistencies
                    ERCC_vector=pandas2ri.ri2py_vector(sizeFactors(ERCC_size))
                    deseq2_vector=pandas2ri.ri2py_vector(sizeFactors(deseq2_size))
                    if len(ERCC_vector) == len(deseq2_vector):
                        for x in range(len(ERCC_vector)):
                            if abs((ERCC_vector[x]-deseq2_vector[x])/(ERCC_vector[x]+deseq2_vector[x])) > 0.1:
                                print('ERCC spike ({x} in list) is greater than 10 percent different than deseq2 size factor for {comparison}.  Will not perform Sleuth overlap for significance. \n'.format(x=x+1,comparison=comparison), file=open(exp.log_file,'a'))
                                print('Samples: ' + str(designs['all_samples']), file=open(exp.log_file,'a'))
                                print('ERCC size factors: ' + str(ERCC_vector), file=open(exp.log_file,'a'))
                                print('DESeq2 size factors: '+ str(deseq2_vector), file=open(exp.log_file,'a'))
                                exp.de_sig_overlap[comparison]=False
                                break
                            else:
                                print('ERCC spike-in is comparable to DESeq2 size-factor, using DESeq2 scaling for {comparison}.  Will perform Sleuth overlap for significance. \n'.format(comparison=comparison), file=open(exp.log_file,'a'))
                                print('Samples: ' + str(designs['all_samples']), file=open(exp.log_file,'a'))
                                print('ERCC size factors: ' + str(ERCC_vector), file=open(exp.log_file,'a'))
                                print('DESeq2 size factors: '+ str(deseq2_vector), file=open(exp.log_file,'a'))
                    else:
                        RaiseError('ERCC and deseq2 column lengths are different for {comparison}'.format(comparison=comparison))

                #DESeq2 results
                exp.de_results['DE2_' + comparison] = pandas2ri.ri2py(as_df(deseq.results(dds[comparison])))
                exp.de_results['DE2_' + comparison].index = data.index
                exp.de_results['DE2_' + comparison].sort_values(by='padj', ascending=True, inplace=True)
                exp.de_results['DE2_' + comparison]['gene_name']=exp.de_results['DE2_'+comparison].index
                exp.de_results['DE2_' + comparison]['gene_name']=exp.de_results['DE2_' + comparison].gene_name.apply(lambda x: x.split("_")[1])
                exp.de_results['DE2_' + comparison].to_csv(out_dir + comparison + '-DESeq2-results.txt', 
                                                           header=True, 
                                                           index=True, 
                                                           sep="\t"
                                                          )
                #Variance Stabilized log2 expected counts.
                exp.de_results[comparison + '_vst'] = pandas2ri.ri2py_dataframe(assay(deseq.varianceStabilizingTransformation(dds[comparison])))
                exp.de_results[comparison + '_vst'].columns = data.columns
                exp.de_results[comparison + '_vst'].index = data.index
                exp.de_results[comparison + '_vst'].to_csv(out_dir + comparison + '-VST-counts.txt', 
                                                           header=True, 
                                                           index=True, 
                                                           sep="\t"
                                                          )

            print(session(), file=open(exp.log_file, 'a'))    
            exp.tasks_complete.append('DESeq2')
            print('DESeq2 differential expression complete: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
            
            return exp

        except:
            print('Error during DESeq2.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error during DESeq2. Fix problem then resubmit with same command to continue from last completed step.')

def Sleuth(exp):
    '''
    Differential expression using sleuth from the Pachter lab: https://pachterlab.github.io/sleuth/
    '''
    if 'Sleuth' in exp.tasks_complete:
        return exp

    else:
        try:

            import pandas as pd
            from rpy2.robjects.packages import importr
            import rpy2.robjects as ro
            from rpy2.robjects import pandas2ri, r, globalenv, Formula
            pandas2ri.activate()
            sleuth = importr('sleuth') 
            biomart = importr('biomaRt')
            dplyr = importr('dplyr', on_conflict="warn")
            session=r("sessionInfo")
            out_dir= exp.scratch + 'Sleuth_results/'
            kal_dir= exp.scratch + 'Kallisto_results/'
            os.makedirs(out_dir, exist_ok=True)

            for comparison,design in exp.designs.items():
                if exp.de_sig_overlap[comparison]:

                    print('Beginning Sleuth differential expression analysis for {comparison}: '.format(comparison=comparison) + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))

                    path = []
                    for name in design['colData'].sample_names.tolist():
                        path.append(kal_dir + name)

                    if 'compensation' in design['colData'].columns.tolist():
                        s2c = pd.DataFrame({'sample': design['colData'].sample_names.tolist(),
                                            'compensation': design['colData'].compensation.tolist(),
                                            'condition': design['colData'].main_comparison.tolist(),
                                            'path': path
                                           },
                                           index=range(1, len(path)+1)
                                          )
                        s2c = s2c[['sample','compensation','condition','path']]
                        condition=Formula('~ compensation + condition')
                        reduced = Formula('~compensation')
                    else:
                        s2c = pd.DataFrame({'sample': design['colData'].sample_names.tolist(),
                                            'condition': design['colData'].main_comparison.tolist(),
                                            'path': path
                                           },
                                           index=range(1, len(path)+1)
                                          )
                        s2c = s2c[['sample','condition','path']]
                        condition=Formula('~ condition')
                        reduced = Formula('~1')

                    

                    globalenv["s2c"] = s2c
                    r('s2c$path = as.character(s2c$path)')
                    s2c = globalenv["s2c"]
                        
                    if exp.genome == 'mm10':
                        mart = biomart.useMart(biomart = "ENSEMBL_MART_ENSEMBL",dataset = "mmusculus_gene_ensembl",host = "useast.ensembl.org")
                    elif exp.genome == 'hg38':
                        mart = biomart.useMart(biomart = "ENSEMBL_MART_ENSEMBL",dataset = "hsapiens_gene_ensembl", host = 'useast.ensembl.org')
                    else:
                       raise RaiseError('Error in sleuth, pipeline only handles hg38 and mm10')

                    t2g = biomart.getBM(attributes = ro.StrVector(("ensembl_transcript_id_version", "ensembl_gene_id","external_gene_name")), mart=mart)
                    t2g = dplyr.rename(t2g, target_id = 'ensembl_transcript_id_version', ens_gene = 'ensembl_gene_id', ext_gene = 'external_gene_name')

                    so = sleuth.sleuth_prep(s2c, target_mapping = t2g, num_cores=1, aggregation_column = 'ens_gene')
                    so = sleuth.sleuth_fit(so, condition, 'full')
                    so = sleuth.sleuth_fit(so, reduced, 'reduced')
                    so = sleuth.sleuth_lrt(so, 'reduced', 'full')
                    print(sleuth.models(so), file=open(exp.log_file,'a'))
                    sleuth_table=sleuth.sleuth_results(so, 'reduced:full','lrt',show_all=True)
                    exp.de_results['SL_' + comparison] = pandas2ri.ri2py(sleuth_table)
                    exp.de_results['SL_' + comparison].to_csv('{out_dir}{comparison}_slueth_results.txt'.format(out_dir=out_dir, comparison=comparison), header=True, index=True, sep="\t")

                else:
                    print('Not performing slueth differential expression analysis for {comparison}.'.format(comparison=comparison), file=open(exp.log_file,'a'))

                print(session(), file=open(exp.log_file, 'a'))    
                print('Sleuth differential expression complete: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
            

            exp.tasks_complete.append('Sleuth')
            return exp

        except:
            print('Error during Sleuth.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error during Sleuth. Fix problem then resubmit with same command to continue from last completed step.')

def sigs(exp):
    '''
    Identifies significantly differentially expressed genes at 2 fold and 1.5 fold cutoffs with q<0.05.
    '''
    if 'Sigs' in exp.tasks_complete:
        return exp

    else:
        try:
            
            for comparison,design in exp.designs.items():

                if exp.de_sig_overlap[comparison]:
                    print('Performing overlaps of signifcant genes from Kallisto/Sleuth and STAR/RSEM/DESeq2 for {comparison}.'.format(comparison=comparison), file=open(exp.log_file,'a'))
               
                    exp.sig_lists[comparison] = {}
                    DE_results=exp.de_results['DE2_'+comparison]
                    SL_results=exp.de_results['SL_'+comparison]
                    SL_sig = set(SL_results[SL_results.qval < 0.05].ext_gene.tolist())

                    DE2_2UP = set(DE_results[(DE_results.padj < 0.05) & (DE_results.log2FoldChange > 1)].gene_name.tolist())
                    DE2_2DN = set(DE_results[(DE_results.padj < 0.05) & (DE_results.log2FoldChange < -1)].gene_name.tolist())
                    DE2_15UP = set(DE_results[(DE_results.padj < 0.05) & (DE_results.log2FoldChange > .585)].gene_name.tolist())
                    DE2_15DN = set(DE_results[(DE_results.padj < 0.05) & (DE_results.log2FoldChange < -.585)].gene_name.tolist())

                    exp.sig_lists[comparison]['2FC_UP'] = DE2_2UP & SL_sig
                    exp.sig_lists[comparison]['2FC_DN'] = DE2_2DN & SL_sig
                    exp.sig_lists[comparison]['15FC_UP'] = DE2_15UP & SL_sig
                    exp.sig_lists[comparison]['15FC_DN'] = DE2_15DN & SL_sig

                else:
                    print('Only using significant genes called from STAR/RSEM/DESeq2 for {comparison} analyses.'.format(comparison=comparison), file=open(exp.log_file, 'a'))
                
                    results=exp.de_results['DE2_'+comparison]

                    exp.sig_lists[comparison] = {}
                    exp.sig_lists[comparison]['2FC_UP'] = set(results[(results.padj < 0.05) & (results.log2FoldChange > 1)].gene_name.tolist())
                    exp.sig_lists[comparison]['2FC_DN'] = set(results[(results.padj < 0.05) & (results.log2FoldChange < -1)].gene_name.tolist())
                    exp.sig_lists[comparison]['15FC_UP'] = set(results[(results.padj < 0.05) & (results.log2FoldChange > .585)].gene_name.tolist())
                    exp.sig_lists[comparison]['15FC_DN'] = set(results[(results.padj < 0.05) & (results.log2FoldChange < -.585)].gene_name.tolist())

            exp.tasks_complete.append('Sigs')
            return exp

        except:
            print('Error during identificaiton of singificantly differentially expressed genes.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error during identificaiton of significantly differentially expressed genes. Fix problem then resubmit with same command to continue from last completed step.')            

def clustermap(exp):
    '''
    Generate heatmap of differentially expressed genes using variance stablized transfrmed log2counts.
    '''
    if 'Heatmaps' in exp.tasks_complete:
        return exp

    else:
        try:
            import matplotlib
            matplotlib.use('agg')
            import seaborn as sns
            
            out_dir=exp.scratch + 'Heatmaps/'
            os.makedirs(out_dir, exist_ok=True)
            
            for comparison,design in exp.designs.items():
                vst = exp.de_results[comparison + '_vst']
                vst['gene_name']=vst.index
                vst['gene_name']=vst.gene_name.apply(lambda x: x.split("_")[1])

                sig = list(exp.sig_lists[comparison]['2FC_UP'] | exp.sig_lists[comparison]['2FC_DN'])
                if len(sig) == 0:
                    print('There are no significantly differentially expressed genes with 2 fold chagnes in {comparison}.  Ignoring heatmap for this group. \n'.format(comparison=comparison), file=open(exp.log_file,'a'))
                else:
                    CM = sns.clustermap(vst[vst.gene_name.apply(lambda x: x in sig)].drop('gene_name',axis=1), z_score=0, method='complete', cmap='RdBu_r')
                    CM.savefig('{out_dir}{comparison}_2FC_Heatmap.png'.format(out_dir=out_dir,comparison=comparison), dpi=200)
                    CM.savefig('{out_dir}{comparison}_2FC_Heatmap.svg'.format(out_dir=out_dir,comparison=comparison), dpi=200)
        
                sig15 = list(exp.sig_lists[comparison]['15FC_UP'] | exp.sig_lists[comparison]['15FC_DN'])
                if len(sig15) == 0:
                    print('There are no significantly differentially expressed genes with 1.5 fold chagnes in {comparison}.  Ignoring heatmap for this group. \n'.format(comparison=comparison), file=open(exp.log_file,'a'))
                else:
                    CM15 = sns.clustermap(vst[vst.gene_name.apply(lambda x: x in sig15)].drop('gene_name',axis=1), z_score=0, method='complete', cmap='RdBu_r')
                    CM15.savefig('{out_dir}{comparison}_1.5FC_Heatmap.png'.format(out_dir=out_dir,comparison=comparison), dpi=200)
                    CM15.savefig('{out_dir}{comparison}_1.5FC_Heatmap.svg'.format(out_dir=out_dir,comparison=comparison), dpi=200)
            
            exp.tasks_complete.append('Heatmaps')
            print('Heatmaps for DESeq2 differentially expressed genes complete: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
            
            return exp

        except:
            print('Error during heatmap generation.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error during heatmap generation. Fix problem then resubmit with same command to continue from last completed step.')

def enrichr(gene_list, description, out_dir):
    '''
    Perform GO enrichment and KEGG enrichment Analysis using Enrichr: http://amp.pharm.mssm.edu/Enrichr/
    '''

    import gseapy
    
    gseapy.enrichr(gene_list=gene_list,
                   description='{description}_KEGG'.format(description=description),
                   gene_sets='KEGG_2016', 
                   outdir=out_dir
                   )
    gseapy.enrichr(gene_list=gene_list,
                   description='{description}_GO_biological_process'.format(description=description),
                   gene_sets='GO_Biological_Process_2017b', 
                   outdir=out_dir
                  )
    gseapy.enrichr(gene_list=gene_list, 
                   description='{description}_GO_molecular_function'.format(description=description),
                   gene_sets='GO_Molecular_Function_2017b', 
                   outdir=out_dir
                  )
    return

def GO_enrich(exp):
    '''
    Perform GO enrichment analysis on significanttly differentially expressed genes.
    '''
    if 'GO_enrich' in exp.tasks_complete:
        return exp

    else:
        try:
            out_dir = exp.scratch + 'GO_Enrichment'
            os.makedirs(out_dir, exist_ok=True)
            
            for comparison,design in exp.designs.items():
                print('Beginning GO enrichment for {comparison}: '.format(comparison=comparison) + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
                
                for name,sig in exp.sig_lists[comparison].items():
                    if len(sig) == 0:
                        print('There are no significantly differentially expressed genes in {name} {comparison}.  Ignoring GO enrichment. \n'.format(name=name,comparison=comparison), file=open(exp.log_file,'a'))
                    else:
                        enrichr(gene_list=list(sig), description='{comparison}_{name}'.format(comparison=comparison,name=name),out_dir=out_dir)

            exp.tasks_complete.append('GO_enrich')
            print('GO Enrichment analysis for DESeq2 differentially expressed genes complete: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
            
            return exp

        except:
            print('Error during GO enrichment.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error during GO enrichment. Fix problem then resubmit with same command to continue from last completed step.')

def GSEA(exp):
    '''
    Perform Gene Set Enrichment Analysis using gsea 3.0 from the Broad Institute.
    '''
    if 'GSEA' in exp.tasks_complete:
        return exp
    else:
        try:
            out_dir = exp.scratch + 'DESeq2_GSEA'
            os.makedirs(out_dir, exist_ok=True)

            if exp.genome == 'mm10':
                mouse2human = pd.read_csv('/projects/ctsi/nimerlab/DANIEL/tools/genomes/genome_conversion/Mouse2Human_Genes.txt', header=None, index_col=0, sep="\t")
                mouse2human_dict=mouse2human[1].to_dict()

            for comparison,design in exp.designs.items():
                
                print('GSEA for {comparison} found in {out}/DESeq2_GSEA/{comparison}. \n'.format(comparison=comparison, out=exp.out_dir), file=open(exp.log_file, 'a'))
                out_compare = '{loc}/{comparison}'.format(loc=out_dir, comparison=comparison)
                os.makedirs(out_compare, exist_ok=True)

                results=exp.de_results['DE2_' + comparison]

                #convert to human homolog if mouse
                if exp.genome == 'mm10':
                    results['gene_name']=results.gene_name.apply(mouse2human_dict)

                results.sort_values(by='stat', ascending=False, inplace=True)
                results.index = results.gene_name
                results = results.stat.dropna()
                results.to_csv('{out_compare}/{comparison}.rnk'.format(out_compare=out_compare, comparison=comparison), header=False, index=True, sep="\t")

                os.chdir(out_compare)

                print('Beginning GSEA enrichment for {comparison}: '.format(comparison=comparison) + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
 
                gmts=['h.all','c2.cp.kegg','c5.bp','c5.mf','c2.cgp']
                for gset in gmts:
                    set_dir=out_compare + '/' + gset 
                    os.makedirs(set_dir, exist_ok=True)

                    command_list = ['module rm python java perl',
                                    'source activate RNAseq',
                                    'java -cp /projects/ctsi/nimerlab/DANIEL/tools/GSEA/gsea-3.0.jar -Xmx2048m xtools.gsea.GseaPreranked -gmx gseaftp.broadinstitute.org://pub/gsea/gene_sets_final/{gset}.v6.1.symbols.gmt -norm meandiv -nperm 1000 -rnk {comparison}.rnk -scoring_scheme weighted -rpt_label {comparison}_{gset} -create_svgs true -make_sets true -plot_top_x 20 -rnd_seed timestamp -set_max 1000 -set_min 10 -zip_report false -out {gset} -gui false'.format(gset=gset,comparison=comparison)
                                   ]

                    exp.job_id.append(send_job(command_list=command_list, 
                                               job_name='{comparison}_{gset}_GSEA'.format(comparison=comparison,gset=gset),
                                               job_log_folder=exp.job_folder,
                                               q= 'general',
                                               mem=3000,
                                               log_file=exp.log_file
                                              )
                                     )
                    time.sleep(1)

            #Wait for jobs to finish
            job_wait(id_list=exp.job_id, job_log_folder=exp.job_folder, log_file=exp.log_file)

            for comparison,design in exp.designs.items():
                if 'index.html' != glob.glob('{loc}/{comparison}/h.all/*/index.html'.format(loc=out_dir, comparison=comparison))[0].split('/')[-1]:
                    raise RaiseError('Error during GSEA for {comparison} submission.'.format(comparison=comparison))


            os.chdir(exp.scratch)
            exp.tasks_complete.append('GSEA')
            print('GSEA using DESeq2 stat preranked genes complete: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
            
            return exp

        except:
            print('Error during GSEA.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error during GSEA. Fix problem then resubmit with same command to continue from last completed step.')

def PCA(exp):

    if 'PCA' in exp.tasks_complete:
        return exp
    else:
        try:

            from sklearn.decomposition import PCA
            import matplotlib
            matplotlib.use('agg')
            import matplotlib.pyplot as plt 
            import matplotlib.patches as mpatches
            
            out_dir = exp.scratch + 'DESeq2_PCA/'
            os.makedirs(out_dir, exist_ok=True)
            
            for comparison,design in exp.designs.items():
                print('Starting PCA analysis for {comparison}: '.format(comparison=comparison) + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
                pca = PCA(n_components=2)
                bpca = bpca=pca.fit_transform(exp.de_results[comparison + '_vst'].drop('gene_name', axis=1).T)
                pca_score = pca.explained_variance_ratio_
                bpca_df = pd.DataFrame(bpca)
                bpca_df.index = exp.de_results[comparison + '_vst'].drop('gene_name',axis=1).T.index
                bpca_df['group']= design['colData']['main_comparison'].tolist()
                bpca_df['name']= design['colData']['sample_names'].tolist()
                    
                fig = plt.clf()
                fig = plt.figure(figsize=(8,8), dpi=100)
                ax = fig.add_subplot(111)
                ax.scatter(bpca_df[bpca_df.group == 'Experimental'][0],bpca_df[bpca_df.group == 'Experimental'][1], marker='o', color='blue')
                ax.scatter(bpca_df[bpca_df.group == 'Control'][0],bpca_df[bpca_df.group == 'Control'][1], marker='o', color='red')
                ax.set_xlabel('PCA Component 1: {var}% variance'.format(var=int(pca_score[0]*100))) 
                ax.set_ylabel('PCA Component 2: {var}% varinace'.format(var=int(pca_score[1]*100)))
                red_patch = mpatches.Patch(color='red', alpha=.4, label='Control')
                blue_patch = mpatches.Patch(color='blue', alpha=.4, label='Experimental')

                for i,sample in enumerate(bpca_df['name'].tolist()):
                    xy=(bpca_df.iloc[i,0], bpca_df.iloc[i,1])
                    ax.annotate(sample, xy= xy, xytext=xy, textcoords='offset points', arrowprops=dict(arrowstyle="-"))             
                ax.legend(handles=[blue_patch, red_patch], loc=1)
                ax.figure.savefig(out_dir + '{comparison}_PCA.png'.format(comparison=comparison))
                ax.figure.savefig(out_dir + '{comparison}_PCA.svg'.format(comparison=comparison))

            exp.tasks_complete.append('PCA')
            print('PCA for DESeq2 groups complete: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))

            return exp

        except:
            print('Error during PCA.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error during PCA. Fix problem then resubmit with same command to continue from last completed step.')

def splicing(exp):
    return exp

def plot_venn2(Series, string_name_of_overlap, folder):
    '''
    Series with with overlaps 10,01,11
    Plots a 2 way venn.
    Saves to file.
    '''
    import matplotlib
    matplotlib.use('agg')
    from matplotlib_venn import venn2
    import matplotlib.pyplot as plt
    
    plt.figure(figsize=(7,7))
    
    font = {'family': 'sans-serif',
            'weight': 'normal',
            'size': 16,
           }
    
    plt.rc('font', **font)
  
    #make venn
    venn_plot = venn2(subsets=(Series.iloc[0], Series.iloc[1], Series.iloc[2]), set_labels = Series.index.tolist())
    patch=['10','01','11']
    colors=['green','blue','teal']
    for patch,color in zip(patch,colors):
        venn_plot.get_patch_by_id(patch).set_color(color)
        venn_plot.get_patch_by_id(patch).set_alpha(0.4)
        venn_plot.get_patch_by_id(patch).set_edgecolor('none')    
     
    plt.title(string_name_of_overlap + " Overlaps")
    plt.tight_layout()
    plt.savefig(folder + string_name_of_overlap + "-overlap-" + datetime.datetime.today().strftime('%Y-%m-%d') + ".svg", dpi=200)
    plt.savefig(folder + string_name_of_overlap + "-overlap-" + datetime.datetime.today().strftime('%Y-%m-%d') + ".png", dpi=200)

def overlaps(exp):
    '''
    Performs overlaps of two or more de_sig lists.
    '''
    if 'Overlap' in exp.tasks_complete:
        return exp
    else:
        try:

            out_dir = exp.scratch + 'Overlaps/'
            os.makedirs(out_dir, exist_ok=True)
            
            names=['2FC_UP', '2FC_DN', '15FC_UP','15FC_DN']
              
            print('Beginning overlap of significant genes: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))

            for overlap,comparison_list in exp.overlaps.items():
                for name in names:
                    key= '{overlap}_{name}'.format(overlap=overlap,name=name)
                    exp.overlap_results[key] = exp.sig_lists[comparison_list[0]][name] & exp.sig_lists[comparison_list[1]][name] 
                    
                    if len(exp.overlap_results[key]) == 0:
                        print('{overlap}_{name} have no overlapping genes'.format(overlap=overlap,name=name), file=open(exp.log_file,'a'))
                    else:
                        venn = pd.Series([len(exp.sig_lists[comparison_list[0]][name])-len(exp.overlap_results[key]),
                                          len(exp.sig_lists[comparison_list[1]][name])-len(exp.overlap_results[key]),
                                          len(exp.overlap_results[key])
                                         ],
                                         index= comparison_list + ['Overlap']
                                        )
                        plot_venn2(venn, key, out_dir)
                    
            for name,sig in exp.overlap_results.items():

                if len(sig) == 0:
                    print('Not performing GO enrichment for {name} overlaps since there are no overlapping genes./\n'.format(name=name), file=open(exp.log_file, 'a'))
                else:
                    print('Performing GO enrichment for {name} overlaps: {time} \n'.format(name=name,time=str(datetime.datetime.now())), file=open(exp.log_file, 'a'))                    
                    enrichr(gene_list=list(sig), description='{name}_overlap'.format(name=name),out_dir=out_dir)

            exp.tasks_complete.append('Overlaps')
            print('Overlap analysis complete: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
                           
            return exp

        except:
            print('Error during overlap analysis.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error during overlap analysis. Fix problem then resubmit with same command to continue from last completed step.')

def final_qc(exp):
    
    if 'MultiQC' in exp.tasks_complete:
        return exp

    else:
        try:

            print('Beginning final qc: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
            
            os.chdir(exp.scratch)

            folder_list=glob.glob(exp.scratch + '/*')
            folders= " ".join(folder_list)
            command_list = ['module rm python',
                            'source activate RNAseq',
                            'multiqc {folders}'.format(folders=folders)
                           ]
            
            exp.job_id.append(send_job(command_list=command_list, 
                                       job_name= 'MultiQC',
                                       job_log_folder=exp.job_folder,
                                       q= 'general',
                                       mem=1000,
                                       log_file=exp.log_file
                                      )
                             )
            
            #Wait for jobs to finish
            job_wait(id_list=exp.job_id, job_log_folder=exp.job_folder, log_file=exp.log_file)
            
            if os.path.isdir(exp.scratch + '/multiqc_data'):
                rmtree(exp.scratch + '/multiqc_data')

            exp.tasks_complete.append('MultiQC')
            
            return exp

        except:
            print('Error during MultiQC.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error during MultiQC. Fix problem then resubmit with same command to continue from last completed step.')

def finish(exp):
    try:
        import yaml

        os.chdir(exp.scratch)
        
        for number,sample in exp.samples.items():
            R_list = ['{loc}{sample}_R1.fastq.gz'.format(loc=exp.fastq_folder,sample=sample),
                      '{loc}{sample}_R2.fastq.gz'.format(loc=exp.fastq_folder,sample=sample)
                     ]
            for R in R_list:
                if os.path.isfile(R):
                    os.remove(R)
        
        print('\nPackage versions: ', file=open(exp.log_file, 'a'))
        with open('/projects/ctsi/nimerlab/DANIEL/tools/nimerlab-pipelines/RNAseq/environment.yml','r') as file:
            versions = yaml.load(file)
        for package in versions['dependencies']:
            print(package, file=open(exp.log_file, 'a'))

        print('\n{name} analysis complete!  Performed the following tasks: '.format(name=exp.name)+ '\n', file=open(exp.log_file, 'a'))
        print(str(exp.tasks_complete) + '\n', file=open(exp.log_file, 'a'))
        
        scratch_log= exp.scratch + exp.name + "-" + exp.date + '.log'
        copy2(exp.log_file, scratch_log)
        rmtree(exp.out_dir)
        copytree(exp.scratch, exp.out_dir)

        exp.tasks_complete.append('Finished')

        filename= '{out}{name}_{date}.pkl'.format(out=exp.out_dir, name=exp.name, date=exp.date)
        with open(filename, 'wb') as experiment:
            pickle.dump(exp, experiment) 

        print('Moved all files into {out}: '.format(out=exp.out_dir) + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
        print("\n Finger's Crossed!!!", file=open(exp.log_file, 'a'))

    except:
        print('Error while finishing pipeline.', file=open(exp.log_file,'a'))
        filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
        with open(filename, 'wb') as experiment:
            pickle.dump(exp, experiment)
        raise RaiseError('Error finishing pipeline. Fix problem then resubmit with same command to continue from last completed step.')

def preprocess(exp):
    exp=fastq_cat(exp)
    exp=stage(exp)
    exp=fastq_screen(exp)
    exp=trim(exp)
    exp=fastqc(exp)  
    return exp

def diff_exp(exp):
    exp = count_matrix(exp)
    exp = DESeq2(exp)
    exp = Sleuth(exp)
    exp = sigs(exp)
    exp = clustermap(exp)
    exp = GO_enrich(exp)
    exp = GSEA(exp)
    exp = PCA(exp)
    #exp = ICA(exp)  
    return exp

def align(exp):
    exp=spike(exp)
    exp=rsem(exp)
    exp=kallisto(exp)
    return exp

def pipeline():
    exp = parse_yaml()
    exp = preprocess(exp)
    exp = align(exp)
    exp = diff_exp(exp)
    exp = overlaps(exp)
    #exp = splicing(exp)
    exp = final_qc(exp)
    finish(exp)

if __name__ == "__main__":
    pipeline()
