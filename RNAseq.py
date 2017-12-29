#!/usr/bin/env python
# coding: utf-8

'''

Nimerlab-RNASeq-pipeline-v0.1

Copyright © 2017-2018 Daniel L. Karl

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation 
files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, 
modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the 
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE 
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR 
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, 
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


Reads an experimetnal design yaml file (Version 0.1).
Requires a conda environment 'RNAseq' made from RNAseq.yml
 
To do:
    - Set up sleuth
    - set analyses for mm10 (convert string)

'''

import os,re,datetime,glob,pickle
from shutil import copy2,copytree,rmtree
import subprocess as sub
import pandas as pd
version=0.1

### Make experiment class
class Experiment(object):
     def __init__(self, scratch, date, name, out_dir, job_folder, qc_folder, 
                  log_file,start,fastq_folder,fastq_start,spike,trimmed,
                  count_matrix,spike_counts,stop,genome,sample_number, 
                  samples, job_id,de_groups,norm,designs, overlaps,
                  tasks_complete,de_results,sig_lists,overlap_results,
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
                           )
    return experiment

class RaiseError(Exception):
    pass

#### Parse Experimental File
def parse_yaml():
    
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

    #Passing paramters to new object
    exp.date = yml['Rundate']   
    exp.name = yml['Name']
    exp.out_dir = yml['Output_directory']
    
    #check whether experiment has been attempted
    filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
    
    if os.path.isfile(filename):
        with open(filename, 'rb') as experiment:
            exp = pickle.load(experiment)
        os.remove(filename)
        return exp 

    else: 

        #Setting Job Folder
        exp.job_folder = exp.scratch + 'logs/'
        os.makedirs(exp.job_folder, exist_ok=True)

        #Log file
        exp.log_file = exp.out_dir + exp.name + "-" + exp.date + '.log'
        
        print('Pipeline version ' + str(version) + ' run on ' + datetime.datetime.today().strftime('%Y-%m-%d') + '\n', file=open(exp.log_file, 'w'))
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
            exp.tasks_complete = exp.tasks_complete + ['Fastq_cat','Stage','FastQC','Fastq_screen','Trim','Spike','RSEM','Kallisto','Count_Matrix']
       
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
        
        #End Point
        if yml['Stop']['Alignment']:
            exp.stop = 'Alignment'
            exp.tasks_complete = exp.tasks_complete + ['DESeq2','DESeq2_Heatmaps','Enrichr_DE','GSEA_DESeq2','PCA','Overlaps']
            print('Pipeline stopping after alignment.'+ '\n', file=open(exp.log_file, 'a'))
        elif yml['Stop']['Differential_Expression']:
            exp.stop = 'DE'
            exp.tasks_complete = exp.tasks_complete + ['DESeq2_Heatmaps','Enrichr_DE','GSEA_DESeq2','PCA','Overlaps']
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
                        print(str(exp.designs)+ '\n', file=open(exp.log_file, 'a')) 
                    else:
                        raise ValueError(error)
        
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
            print('Overlapping ' + str(len(list(exp.overlaps.keys()))) + ' differential analysis comparison(s).'+ '\n', file=open(exp.log_file, 'a'))
            print(str(exp.overlaps)+ '\n', file=open(exp.log_file, 'a'))
            
        #Initialized Process Complete List
        exp.tasks_complete.append('Parsed')

        print('Experiment file parsed: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
        
        return exp

# Sends job to LSF resource manager queues
def send_job(command_list, job_name, job_log_folder, q, mem):
    
    import random
    
    os.makedirs(job_log_folder, exist_ok=True)

    '''
    Send job to LSF pegasus.ccs.miami.edu
    Example:
    print(send_job(command_list=['module rm python,
                                  'source activate RNAseq' ,
                                  'fastqc...  ',
                                  'fastq_screen.... ' 
                                 ], 
                   job_name='fastqc',
                   job_log_folder=exp.job_folder,
                   q='bigmem',
                   mem=60000
                  )
         )
    '''

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
    write_job = open(job_path_name, 'a')
    write_job.write(cmd)
    write_job.close()
    print(cmd+ '\n', file=open(exp.log_file, 'a'))
    os.system('bsub < {}'.format(job_path_name))
    print('sending job ID_' + str(rand_id) + '...'+ '\n', file=open(exp.log_file, 'a'))
   
    return rand_id

# waits for LSF jobs to finish
def job_wait(rand_id, job_log_folder):
    
    running = True
    time = 0
    while running:
        jobs_list = os.popen('sleep 30|bhist -w').read()
        print('Waiting for jobs to finish... {}'.format(str(datetime.datetime.now())), file=open(exp.log_file, 'a'))

        if len([j for j in re.findall('ID_(\d+)', jobs_list) if j == rand_id]) == 0:
            running = False
        else:
            time += 10
    
def fastq_cat(exp):
    
    
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


# Stages experiment in a scratch folder
def stage(exp):
    
    if 'Stage' in exp.tasks_complete:
        return exp

    else:

        set_temp='/scratch/projects/nimerlab/tmp'
        sub.run('export TMPDIR=' + set_temp, shell=True)
        print('TMP directory set to ' + set_temp+ '\n', file=open(exp.log_file, 'a'))
        
        #Stage Experiment Folder in Scratch
        os.makedirs(exp.scratch, exist_ok=True)
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
    
    if 'FastQC' in exp.tasks_complete:
        return exp

    else:
        try:
            print('Assessing fastq quality.'+ '\n', file=open(exp.log_file, 'a'))

            #Make QC folder
            exp.qc_folder = exp.scratch + 'QC/'
            os.makedirs(exp.qc_folder, exist_ok=True)
            
            #Submit fastqc and fastq_screen jobs for each sample
            if exp.trimmed == False:
                
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
                                               mem=1000
                                              )
                                     )
            elif exp.trimmed:

                for number,sample in exp.samples.items():
                    command_list = ['module rm python',
                                    'module rm perl',
                                    'source activate RNAseq',
                                    'fastqc ' + exp.fastq_folder + sample + '_trim_*',
                                   ]

                    exp.job_id.append(send_job(command_list=command_list, 
                                               job_name= sample + '_fastqc_trim',
                                               job_log_folder=exp.job_folder,
                                               q= 'general',
                                               mem=1000
                                              )
                                     )
            else:
                raise ValueError("Error processing trimming status.")
            
            #Wait for jobs to finish
            for rand_id in exp.job_id:
                job_wait(rand_id=rand_id, job_log_folder=exp.job_folder)
            
            #move to qc folder
            fastqc_files = glob.glob(exp.fastq_folder + '*.zip')
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
                                           mem=1000
                                          )
                                 )
            
            #Wait for jobs to finish
            for rand_id in exp.job_id:
                job_wait(rand_id=rand_id, job_log_folder=exp.job_folder)
            
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

# Trimming based on standard UM SCCC Core Nextseq 500 technical errors
def trim(exp):

    if 'Trim' in exp.tasks_complete:
        exp.trimmed = True
        return exp

    else:
        try:
            print('Beginning fastq trimming: '  + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
                
            #change to experimental directory in scratch
            os.chdir(exp.fastq_folder)

            #Submit fastqc and fastq_screen jobs for each sample
            for number,sample in exp.samples.items():
                print('Trimming {sample}: '.format(sample=sample)+ '\n', file=open(exp.log_file, 'a'))
                
                trim_galore= 'trim_galore --clip_R1 2 --clip_R2 2 --paired --three_prime_clip_R1 4 --three_prime_clip_R2 4 {loc}{sample}_R1.fastq.gz {loc}{sample}_R2.fastq.gz'.format(loc=exp.fastq_folder,sample=sample) 
                skewer='skewer --mode pe --end-quality 20 --compress --min 18 --threads 15 -n {loc}{sample}_R1_val_1.fq.gz {loc}{sample}_R2_val_2.fq.gz'.format(loc=exp.fastq_folder,sample=sample)

                command_list = ['module rm python',
                                'module rm perl',
                                'source activate RNAseq',
                                trim_galore,
                                skewer
                               ]

                exp.job_id.append(send_job(command_list=command_list, 
                                           job_name= sample + '_trim',
                                           job_log_folder=exp.job_folder,
                                           q= 'general',
                                           mem=1000
                                          )
                                 )
            
            #Wait for jobs to finish
            for rand_id in exp.job_id:
                job_wait(rand_id=rand_id, job_log_folder=exp.job_folder)
            
            
            for number,sample in exp.samples.items():
                os.rename('{loc}{sample}_R1_val_1.fq-trimmed-pair1.fastq.gz'.format(loc=exp.fastq_folder,sample=sample),
                          '{loc}{sample}_trim_R1.fastq.gz'.format(loc=exp.fastq_folder,sample=sample)
                         )
                
                os.rename('{loc}{sample}_R1_val_1.fq-trimmed-pair2.fastq.gz'.format(loc=exp.fastq_folder,sample=sample),
                          '{loc}{sample}_trim_R2.fastq.gz'.format(loc=exp.fastq_folder,sample=sample)
                         )
                os.remove('{loc}{sample}_R1_val_1.fq.gz'.format(loc=exp.fastq_folder,sample=sample))
                os.remove('{loc}{sample}_R2_val_2.fq.gz'.format(loc=exp.fastq_folder,sample=sample))

            #move logs to qc folder        
            logs = glob.glob(exp.fastq_folder + '*.txt')
            logs = logs + glob.glob(exp.fastq_folder + '*.log')
            for l in logs:
                copy2(l,exp.qc_folder) 
                os.remove(l)

            exp.trimmed = True

            #change to experimental directory in scratch
            os.chdir(exp.scratch)
            exp.tasks_complete.append('Trim')
            print('Trimming complete: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
            
            return exp
        except:
            print('Error in trimming.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error during trimming. Fix problem then resubmit with same command to continue from last completed step.')

def preprocess(exp):
    
    exp=fastq_cat(exp)
    exp=stage(exp)
    exp=fastq_screen(exp)
    exp=trim(exp)
    exp=fastqc(exp)  
    
    return exp

def spike(exp):
    
    if 'Spike' in exp.tasks_complete:
        return exp

    elif exp.spike:
        try:
            print("Processing with ERCC spike-in: " + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
            
            ERCC_folder=exp.scratch + 'ERCC/'
            os.makedirs(ERCC_folder, exist_ok=True)

            #Submit STAR alingment for spike-ins for each sample
            for number,sample in exp.samples.items():
                print('Aligning {sample} to spike-in.'.format(sample=sample)+ '\n', file=open(exp.log_file, 'a'))

                spike='STAR --runThreadN 10 --genomeDir /projects/ctsi/nimerlab/DANIEL/tools/genomes/ERCC_spike/STARIndex --readFilesIn {loc}{sample}_trim_R1.fastq.gz {loc}{sample}_trim_R2.fastq.gz --readFilesCommand zcat --outFileNamePrefix {loc}{sample}_ERCC --quantMode GeneCounts'.format(loc=ERCC_folder,sample=sample)

                command_list = ['module rm python',
                                'module rm perl',
                                'source activate RNAseq',
                                spike
                               ]

                exp.job_id.append(send_job(command_list=command_list, 
                                           job_name= sample + '_ERCC',
                                           job_log_folder=exp.job_folder,
                                           q= 'general',
                                           mem=5000
                                          )
                                 )

            #Wait for jobs to finish
            for rand_id in exp.job_id:
                job_wait(rand_id=rand_id, job_log_folder=exp.job_folder)
            
            ### Generate one matrix for all spike_counts
            matrix='rsem-generate-data-matrix '
            columns=[]
            for number,sample in exp.samples.items():
                matrix = matrix + '{loc}{sample}_ERCCReadsPerGene.out.tab '.format(loc=ERCC_folder, sample=sample)
                columns.append(sample)
            
            matrix = matrix + '> {loc}ERCC.count.matrix'.format(loc=ERCC_folder)
            
            command_list = ['module rm python',
                            'source activate RNAseq',
                            matrix
                           ]

            exp.job_id.append(send_job(command_list=command_list, 
                                       job_name= 'ERCC_Count_Matrix',
                                       job_log_folder=exp.job_folder,
                                       q= 'general',
                                       mem=1000
                                      )
                             )
            
            #Wait for jobs to finish
            for rand_id in exp.job_id:
                job_wait(rand_id=rand_id, job_log_folder=exp.job_folder)
            
            try:
                exp.spike_counts = pd.read_csv('{loc}ERCC.count.matrix'.format(loc=ERCC_folder),
                                               header=0,
                                               index_col=0,
                                               sep="\t")
            except:
                print('Error loading spike_counts.', file=open(exp.log_file,'a'))
                filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
                with open(filename, 'wb') as experiment:
                    pickle.dump(exp, experiment)
                raise RaiseError('Error loading spike_counts. Make sure the file is not empty.')
            
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
    
    if 'RSEM' in exp.tasks_complete:
        return exp

    else:
        try:    
            print('Beginning RSEM-STAR alignments: '  + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
            
            if exp.genome == 'hg38':
                #Submit RSEM-STAR for each sample
                for number,sample in exp.samples.items():
                    print('Aligning using STAR and counting transcripts using RSEM for {sample}.'.format(sample=sample)+ '\n', file=open(exp.log_file, 'a'))

                    align='rsem-calculate-expression --star --star-gzipped-read-file --paired-end --append-names --output-genome-bam --sort-bam-by-coordinate -p 15 {loc}{sample}_trim_R1.fastq.gz {loc}{sample}_trim_R2.fastq.gz /projects/ctsi/nimerlab/DANIEL/tools/genomes/H_sapiens/Ensembl/GRCh38/Sequence/RSEM_STARIndex/human {sample}'.format(loc=exp.fastq_folder,sample=sample)
                    bam2wig='rsem-bam2wig {sample}.genome.sorted.bam {sample}.wig {sample}'.format(sample=sample)
                    wig2bw='wigToBigWig {sample}.wig /projects/ctsi/nimerlab/DANIEL/tools/genomes/H_sapiens/Ensembl/GRCh38/Sequence/RSEM_STARIndex/chrNameLength.txt {sample}.rsem.bw'.format(sample=sample)
                    plot_model='rsem-plot-model {sample} {sample}.models.pdf'

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
                                                mem=60000
                                                )
                                      )
            elif exp.genome =='mm10':
                #Submit RSEM-STAR for each sample
                for number,sample in exp.samples.items():
                    print('Aligning using STAR and counting transcripts using RSEM for {sample}.'.format(sample=sample)+ '\n', file=open(exp.log_file, 'a'))

                    align='rsem-calculate-expression --star --star-gzipped-read-file --paired-end --append-names --output-genome-bam --sort-bam-by-coordinate -p 15 {loc}{sample}_trim_R1.fastq.gz {loc}{sample}_trim_R2.fastq.gz /projects/ctsi/nimerlab/DANIEL/tools/genomes/Mus_musculus/Ensembl/GRCm38/Sequence/RSEM_STARIndex/mouse {sample}'.format(loc=exp.fastq_folder,sample=sample)
                    bam2wig='rsem-bam2wig {sample}.genome.sorted.bam {sample}.wig {sample}'.format(sample=sample)
                    wig2bw='wigToBigWig {sample}.wig /projects/ctsi/nimerlab/DANIEL/tools/genomes/Mus_musculus/Ensembl/GRCm38/Sequence/RSEM_STARIndex/chrNameLength.txt {sample}.rsem.bw'.format(sample=sample)
                    plot_model='rsem-plot-model {sample} {sample}.models.pdf'

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
                                                mem=60000
                                                )
                                     )
            else:
                print('Error in star/rsem alignment, cannot align to genome other than mm10 or hg38.', file=open(exp.log_file,'a'))
                filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
                with open(filename, 'wb') as experiment:
                    pickle.dump(exp, experiment)
                raise IOError('This pipeline only handles mm10 or hg38 genomes.  Please fix and resubmit.')

            #Wait for jobs to finish
            for rand_id in exp.job_id:
                job_wait(rand_id=rand_id, job_log_folder=exp.job_folder)
             
            #make RSEM_results folder
            os.makedirs(exp.scratch + 'RSEM_results/', exist_ok=True)
            
            #move results to folder        
            results = glob.glob(exp.scratch + '*.models.pdf')
            results.append(glob.glob(exp.scratch + '*.genes.results'))
            results.append(glob.glob(exp.scratch + '*.isoforms.results'))
            results.append(glob.glob(exp.scratch + '*.genome.sorted.bam'))
            results.append(glob.glob(exp.scratch + '*.genome.sorted.bam.bai'))
            results.append(glob.glob(exp.scratch + '*.rsem.bw RSEM_results'))
            for file in results:
                copy2(file,exp.scratch + 'RSEM_results/')
                os.remove(file)

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
    
    if 'Kallisto' in exp.tasks_complete:
        return exp

    else:
        try:
            print('Beginning Kallisto alignments: '  + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
            
            #make Kallisto_results folder
            os.makedirs(exp.scratch + 'Kallisto_results/', exist_ok=True)
            
            if exp.genome == 'hg38':
                #Submit kallisto for each sample
                for number,sample in exp.samples.items():
                    print('Aligning {sample} using Kallisto.'.format(sample=sample)+ '\n', file=open(exp.log_file, 'a'))

                    align='kallisto quant --index=/projects/ctsi/nimerlab/DANIEL/tools/genomes/H_sapiens/Ensembl/GRCh38/Sequence/KallistoIndex/GRCh38.transcripts.idx --output-dir={out}Kallisto_results --threads=15 --bootstrap-samples=100 {loc}{sample}_trim_R1.fastq.gz {loc}{sample}_trim_R2.fastq.gz'.format(out=exp.scratch,loc=exp.fastq_folder,sample=sample)

                    command_list = ['module rm python',
                                    'module rm perl',
                                    'source activate RNAseq',
                                    align
                                    ]

                    exp.job_id.append(send_job(command_list=command_list, 
                                                job_name= sample + '_Kallisto',
                                                job_log_folder=exp.job_folder,
                                                q= 'bigmem',
                                                mem=60000
                                                )
                                      )
            elif exp.genome == 'mm10':
                #Submit kallisto for each sample
                for number,sample in exp.samples.items():
                    print('Aligning {sample} using Kallisto.'.format(sample=sample)+ '\n', file=open(exp.log_file, 'a'))

                    align='kallisto quant --index=/projects/ctsi/nimerlab/DANIEL/tools/genomes/Mus_musculus/Ensembl/GRCm38/Sequence/KallistoIndex/GRCm38.transcripts.idx --output-dir={out}Kallisto_results --threads=15 --bootstrap-samples=100 {loc}{sample}_trim_R1.fastq.gz {loc}{sample}_trim_R2.fastq.gz'.format(out=exp.scratch,loc=exp.fastq_folder,sample=sample)

                    command_list = ['module rm python',
                                    'module rm perl',
                                    'source activate RNAseq',
                                    align
                                    ]

                    exp.job_id.append(send_job(command_list=command_list, 
                                                job_name= sample + '_Kallisto',
                                                job_log_folder=exp.job_folder,
                                                q= 'bigmem',
                                                mem=60000
                                                )
                                      )

            else:
                print('Error in kallisto, cannot align to genome other than mm10 or hg38.', file=open(exp.log_file,'a'))
                filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
                with open(filename, 'wb')  as experiment:
                    pickle.dump(exp, experiment)
                raise IOError('This pipeline only handles mm10 or hg38 genomes.  Please fix and resubmit.')

            #Wait for jobs to finish
            for rand_id in exp.job_id:
                job_wait(rand_id=rand_id, job_log_folder=exp.job_folder)
            
            exp.tasks_complete.append('Kallisto')
            
            return exp

        except:
            print('Error during Kallisto alignment.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error during Kallisto alignment. Fix problem then resubmit with same command to continue from last completed step.')


def align(exp):
    
    exp=spike(exp)
    exp=rsem(exp)
    exp=kalliso(exp)

    ## handle stop after alignment
    return exp


def count_matrix(exp):
    
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
                                       mem=1000
                                      )
                             )
            
            #Wait for jobs to finish
            for rand_id in exp.job_id:
                job_wait(rand_id=rand_id, job_log_folder=exp.job_folder)
            
            counts = pd.read_csv('{loc}RSEM.count.matrix'.format(loc=(exp.scratch + 'RSEM_results/')), header=0, index_col=0, sep="\t")
            counts.columns = columns
            
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
            ro.pandas2ri.activate()
            
            deseq = ro.packages.importr('DESeq2')
            as_df=ro.r("as.data.frame")
            assay=ro.r("assay")
            session=ro.r("sessionInfo")
            
            out_dir= exp.scratch + 'DESeq2_results/'
            os.makedirs(out_dir, exist_ok=True)
            
            count_matrix = exp.count_matrix
            dds={}
            
            for comparison,design in exp.design.items():
                print('Beginning ' + comparison + ': ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
                colData=design['colData']
                design=design['design']
                data=count_matrix[design['all_samples']]
                dds[comparison] = deseq.DESeqDataSetFromMatrix(countData = data.values,
                                                               colData=colData,
                                                               design=design
                                                              )
                
                print('Performing differential expression with DESeq2: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
                dds[comparison] = deseq.DESeq(dds[comparison])
                
                if exp.norm == 'ERCC':
                    print('Determining ERCC size factors...'+ '\n', file=open(exp.log_file, 'a'))
                    ERCC_data = exp.spike_counts[design['all_samples']]
                    ERCC_dds = deseq.DESeqDataSetFromMatrix(countData = ERCC_data.values, colData=colData, design=design)
                    ERCC_size = deseq.estimateSizeFactors_DESeqDataSet(ERCC_dds)
                    sizeFactors=robjects.r("sizeFactors")
                    dds[comparison].do_slot('colData').do_slot('listData')[1] = sizeFactors(ERCC_size)
                    dds[comparison] = deseq.DESeq(dds[comparison])
                
                #DESeq2 results
                exp.de_results[comparison] = ro.pandas2ri.ri2py(as_df(deseq.results(dds[comparison])))
                exp.de_results[comparison].index = data.index
                exp.de_results[comparison].sort_values(by='padj', ascending=True, inplace=True)
                exp.de_results[comparison]['gene_name']=exp.de_results[comparison].index
                exp.de_results[comparison].to_csv(out_dir + comparison + '-DESeq2-results.txt', 
                                                  header=True, 
                                                  index=True, 
                                                  sep="\t"
                                                 )
                #Variance Stabilized log2 expected counts.
                exp.de_results[comparison + '_vst'] = ro.pandas2ri.ri2py_dataframe(assay(deseq.varianceStabilizingTransformation(dds[comparison])))
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
    

def clustermap(exp):
    
    if 'DESeq2_Heatmaps' in exp.tasks_complete:
        return exp

    else:
        try:

            import seaborn as sns
            
            os.makedirs(exp.scratch + 'DESeq2_results/Heatmaps/', exist_ok=True)
            
            for comparison,design in exp.design.items():
                results=exp.de_results[comparison]
                vst = exp.de_results[comparison + '_vst']
                sig = results[(results.padj < 0.05) & ((results.log2FoldChange > 1) | (results.log2FoldChange < -1))].gene_name.tolist()
                CM = sns.clustermap(vst[vst.gene_name.apply(lambda x: x in sig)], z_score=0, method='complete', cmap='RdBu_r')
                CM.savefig(exp.scratch + 'DESeq2_results/Heatmaps/{comparison}_2FC_Heatmap.png'.format(comparison=comparison), dpi=200)
                CM.savefig(exp.scratch + 'DESeq2_results/Heatmaps/{comparison}_2FC_Heatmap.png'.format(comparison=comparison), dpi=200)
            
                sig15 = results[(results.padj < 0.05) & ((results.log2FoldChange > 0.585) | (results.log2FoldChange < -0.585))].gene_name.tolist()
                CM15 = sns.clustermap(vst[vst.gene_name.apply(lambda x: x in sig15)], z_score=0, method='complete', cmap='RdBu_r')
                CM15.savefig(exp.scratch + 'DESeq2_results/Heatmaps/{comparison}_1.5FC_Heatmap.png'.format(comparison=comparison), dpi=200)
                CM15.savefig(exp.scratch + 'DESeq2_results/Heatmaps/{comparison}_1.5FC_Heatmap.svg'.format(comparison=comparison), dpi=200)
            
            exp.tasks_complete.append('DESeq2_Heatmaps')
            print('Heatmaps for DESeq2 differentially expressed genes complete: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
            
            return exp

        except:
            print('Error during heatmap generation.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error during heatmap generation. Fix problem then resubmit with same command to continue from last completed step.')

def enrichr_de(exp):
    
    if 'Enrichr_DE' in exp.tasks_complete:
        return exp

    else:
        try:

            import gseapy
            
            out_dir = exp.scratch + 'DESeq2_results/enrichr'
            os.makedirs(out_dir, exist_ok=True)
            
            for comparison,design in exp.design.items():
                print('Beginning GO enrichment for {comparison}: '.format(comparison=comparison) + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
                
                results=exp.de_results[comparison]
                results['gene_name']=results.gene_name.apply(lambda x: x.split("_")[1])
                
                exp.sig_lists[comparison] = {}
                exp.sig_lists[comparison]['2FC_UP'] = set(results[(results.padj < 0.05) & (results.log2FoldChange > 1)].gene_name.tolist())
                exp.sig_lists[comparison]['2FC_DN'] = set(results[(results.padj < 0.05) & (results.log2FoldChange < -1)].gene_name.tolist())
                exp.sig_lists[comparison]['15FC_UP'] = set(results[(results.padj < 0.05) & (results.log2FoldChange > .585)].gene_name.tolist())
                exp.sig_lists[comparison]['15FC_DN'] = set(results[(results.padj < 0.05) & (results.log2FoldChange < -.585)].gene_name.tolist())

                for name,sig in exp.sig_lists[comparison].items():
                    gseapy.enrichr(gene_list=list(sig), 
                                   description='{comparison}_{name}_KEGG'.format(comparison=comparison,name=name),
                                   gene_sets='KEGG_2016', 
                                   outdir=out_dir
                                  )
                    gseapy.enrichr(gene_list=list(sig), 
                                   description='{comparison}_{name}_GO_biological_process'.format(comparison=comparison,name=name), 
                                   gene_sets='GO_Biological_Process_2017b', 
                                   outdir=out_dir
                                  )
                    gseapy.enrichr(gene_list=list(sig), 
                                   description='{comparison}_{name}_GO_molecular_function'.format(comparison=comparison,name=name), 
                                   gene_sets='GO_Molecular_Function_2017b', 
                                   outdir=out_dir
                                  )
                        
            
            exp.tasks_complete.append('Enrichr_DE')
            print('Enrichment analysis for DESeq2 differentially expressed genes complete: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
            
            return exp

        except:
            print('Error during Enrichr.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error during Enrichr. Fix problem then resubmit with same command to continue from last completed step.')

def GSEA(exp):
    
    if 'GSEA' in exp.tasks_complete:
        return exp

    else:
        try:

            import geseapy
            
            out_dir = exp.scratch + 'DESeq2_results/GSEA'
            os.makedirs(out_dir, exist_ok=True)
            
            for comparison,design in exp.design.items():
                
                print('Beginning GSEA for {comparison} found in {out}/DESeq2/GSEA/{comparison}. \n'.format(comparison=comparison, out=exp.out_dir), file=open(exp.log_file, 'a'))
                out_compare = '{loc}/{comparison}'.format(loc=out_dir, comparison=comparison)
                os.makedirs(out_compare, exist_ok=True)

                print('Beginning GSEA enrichment for {comparison}: '.format(comparison=comparison) + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
                results=exp.de_results[comparison]
                results['gene_name']=results.gene_name.apply(lambda x: x.split("_")[1])
                results.sort_values(by='stat', ascending=False, inplace=True)
                
                print('Beginning GSEA:Hallmark enrichment for {comparison}: '.format(comparison=comparison) + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
                gseapy.prerank(rnk= results.stat, gene_sets= '/projects/ctsi/nimerlab/DANIEL/tools/gene_sets/h.all.v6.1.symbols.gmt', outdir=out_compare)
                print('Beginning GSEA:KEGG enrichment for {comparison}: '.format(comparison=comparison) + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
                gseapy.prerank(rnk= results.stat, gene_sets= '/projects/ctsi/nimerlab/DANIEL/tools/gene_sets/c2.cp.kegg.v6.1.symbols.gmt', outdir=out_compare)
                print('Beginning GSEA:GO biological process enrichment for {comparison}: '.format(comparison=comparison) + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
                gseapy.prerank(rnk= results.stat, gene_sets= '/projects/ctsi/nimerlab/DANIEL/tools/gene_sets/c5.bp.v6.1.symbols.gmt', outdir=out_compare)
                print('Beginning GSEA:GO molecular function enrichment for {comparison}: '.format(comparison=comparison) + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
                gseapy.prerank(rnk= results.stat, gene_sets= '/projects/ctsi/nimerlab/DANIEL/tools/gene_sets/c5.mf.v6.1.symbols.gmt', outdir=out_compare)
                print('Beginning GSEA:Perturbation enrichment for {comparison}: '.format(comparison=comparison) + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
                gseapy.prerank(rnk= results.stat, gene_sets= '/projects/ctsi/nimerlab/DANIEL/tools/gene_sets/c2.cgp.v6.1.symbols.gmt', outdir=out_compare)

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
            import matplotlib.pyplot as plt 
            import matplotlib.patches as mpatches
            
            out_dir = exp.scratch + 'DESeq2_results/PCA/'
            os.makedirs(out_dir, exist_ok=True)
            
            for comparison,design in exp.design.items():
                print('Starting PCA analysis for {comparison}: '.format(comparison=comparison) + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
                pca = PCA(n_components=2)
                bpca = bpca=pca.fit_transform(exp.de_results[comparison + '_vst'].T)
                pca_score = pca.explained_variance_ratio_
                bpca_df = pd.DataFrame(bpca)
                bpca_df.index = exp.de_results[comparison + '_vst'].T.index
                bpca_df['group']= design['colData']['main_comparison'].tolist()
                bpca_df['name']= design['colData']['sample_names'].tolist()
                    
                plt.clf()
                fig = plt.figure(figsize=(8,8), dpi=100)
                ax = fig.add_subplot(111)
                ax.scatter(bpca_df[bpca_df.group == 'Experimental'][0],bpca_df[bpca_df.group == 'Experimental'][1], marker='o', color='blue')
                ax.scatter(bpca_df[bpca_df.group == 'Control'][0],bpca_df[bpca_df.group == 'Control'][1], marker='o', color='red')
                ax.set_xlabel('PCA Component 1: {var}% variance'.format(var=int(pca_score[0]*100))) 
                ax.set_ylabel('PCA Component 2: {var}% varinace'.format(var=int(pca_score[1]*100)))
                red_patch = mpatches.Patch(color='red', alpha=.4, label='Control')
                blue_patch = mpatches.Patch(color='blue', alpha=.4, label='Experimental')

                for i,sample in enumerate(bpca_df['name'].tolist()):
                    ax.annotate(sample, (bpca_df.iloc[i,0], bpca_df.iloc[i,1]), textcoords='offset points')             
                ax.legend(handles=[blue_patch, red_patch], loc=1)
                ax.figure.savefig(out_dir, '{comparison}_PCA.png'.format(comparison=comparison))
                ax.figure.savefig(out_dir, '{comparison}_PCA.svg'.format(comparison=comparison))

            exp.tasks_complete.append('PCA')
            print('PCA for DESeq2 groups complete: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))

            return exp

        except:
            print('Error during PCA.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error during PCA. Fix problem then resubmit with same command to continue from last completed step.')

def diff_exp(exp):
    
    exp = count_matrix(exp)
    exp = spike_norm(exp)
    exp = DESeq2(exp)
    exp = clustermap(exp)
    exp = enrichr_de(exp)
    exp = GSEA(exp)
    exp = PCA(exp)
    #Sleuth
    #ICA  

    return exp


def plot_venn2(Series, string_name_of_overlap, folder):
    '''
    Series with with overlaps 10,01,11
    Plots a 2 way venn.
    Saves to file.
    '''
    
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
    
    if 'Overlap' in exp.tasks_complete:
        return exp

    else:
        try:

            import gseapy
            
            out_dir = exp.scratch + 'Overlaps/'
            os.makedirs(out_dir, exist_ok=True)
            
            names=['2FC_UP', '2FC_DN', '15FC_UP','15FC_DN']
              
            print('Beginning overlap of significant genes: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))

            for overlap,comparison_list in exp.overlaps.items():
                for name in names:
                    key= '{overlap}_{name}'.format(overlap=overlap,name=name)
                    exp.overlap_results[key] = exp.sig_lists[comparison_list[0]][name] & exp.sig_lists[comparison_list[1]][name] 
                    venn = pd.Series([len([comparison_list[0]][name])-len(exp.overlap_results[key]),
                                      len([comparison_list[1]][name])-len(exp.overlap_results[key]),
                                      len(exp.overlap_results[key])
                                     ],
                                     index= [comparison_list] + ['Overlap']
                                    )
                    plot_venn2(venn, key, out_dir)
                           
            for name,sig in exp.overlap_results.items():
                print('Perfomring GO enrichment for ' + name + ' overlaps: ' + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))
                gseapy.enrichr(gene_list=list(sig),
                               description='{name}_overlap_KEGG'.format(name=name),
                               gene_sets='KEGG_2016', 
                               outdir=out_dir
                              )
                gseapy.enrichr(gene_list=list(sig),
                               description='{name}_overlap_GO_biological_process'.format(name=name),
                               gene_sets='GO_Biological_Process_2017b', 
                               outdir=out_dir
                              )
                gseapy.enrichr(gene_list=list(sig), 
                               description='{name}_overlap_GO_molecular_function'.format(name=name),
                               gene_sets='GO_Molecular_Function_2017b', 
                               outdir=out_dir
                              )
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
            
            command_list = ['module rm python',
                            'source activate RNAseq',
                            'multiqc {folders}'.format(folders=exp.scratch)
                           ]
            
            exp.job_id.append(send_job(command_list=command_list, 
                                       job_name= 'MultiQC',
                                       job_log_folder=exp.job_folder,
                                       q= 'general',
                                       mem=1000
                                      )
                             )
            
            #Wait for jobs to finish
            for rand_id in exp.job_id:
                job_wait(rand_id=rand_id, job_log_folder=exp.job_folder)
            
            exp.tasks_complete.append('MultiQC')
            
            return exp

        except:
            print('Error during MultiQC.', file=open(exp.log_file,'a'))
            filename= '{out}{name}_{date}_incomplete.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
            with open(filename, 'wb') as experiment:
                pickle.dump(exp, experiment)
            raise RaiseError('Error during MultiQC. Fix problem then resubmit with same command to continue from last completed step.')

def finish(exp):
    
    import yaml

    filename= '{out}{name}_{date}.pkl'.format(out=exp.scratch, name=exp.name, date=exp.date)
    with open(filename, 'wb') as experiment:
        pickle.dump(exp, experiment) 
    
    for number,sample in exp.samples.items():
        os.remove('{loc}{sample}_R1.fastq.gz'.format(loc=exp.fastq_folder,sample=sample))
        os.remove('{loc}{sample}_R2.fastq.gz'.format(loc=exp.fastq_folder,sample=sample))
    
    copytree(exp.scratch, exp.outdir)
    
    print('{name} analysis complete!  Performed the following tasks: '.format(name=exp.name)+ '\n', file=open(exp.log_file, 'a'))
    print(str(exp.tasks_complete) + '\n', file=open(exp.log_file, 'a'))
    print('Moved all files into {out}: '.format(out=exp.outdir) + str(datetime.datetime.now())+ '\n', file=open(exp.log_file, 'a'))

    with open('/projects/ctsi/nimerlab/DANIEL/tools/nimerlab-pipelines/RNAseq/environment.yml','r') as file:
        versions = yaml.load(file)

    print('Package versions: ', file=open(exp.log_file, 'a'))
    for package in versions['dependencies']:
        print(package, file=open(exp.log_file, 'a'))

    print("\n Finger's Crossed!!!", file=open(exp.log_file, 'a'))
    

### Pipeline:

exp = parse_yaml()
exp = preprocess(exp)
exp = align(exp)
exp = diff_exp(exp) #finetune for cluster map
exp = Overlaps(exp)
exp = final_qc(exp)
finish(exp)
