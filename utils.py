import logging
import subprocess
import os
import sys
import re
import warnings
import pysam
from distutils.version import LooseVersion
# Check java version to make sure it is Java 8
MY_DIR = os.path.dirname(os.path.realpath(__file__))
VARSIMJAR = os.path.realpath(os.path.join(MY_DIR, "VarSim.jar"))
RTGJAR = os.path.realpath(os.path.join(MY_DIR, "RTG.jar"))
SORT_VCF = os.path.realpath(os.path.join(MY_DIR, "src","sort_vcf.sh"))
BGZIP = os.path.realpath(os.path.join(MY_DIR, "opt","htslib-1.9_install/bin/bgzip"))
JAVA_XMX = "-Xmx"
DEFAULT_JAVA = os.path.realpath(os.path.join(MY_DIR, "opt",
                                "jdk1.8.0_131", "bin", "java"))
DEFAULT_PYTHON = os.path.realpath(os.path.join(MY_DIR, "opt", "miniconda2", "bin", "python"))
COMBINE_KEEP_ALL_DUPLICATE = 1
COMBINE_KEEP_FIRST_DUPLICATE = 2
COMBINE_KEEP_NO_DUPLICATE = 3

def get_java(java = "java"):
    '''
    return default java if it exists, otherwise use user-specificed version
    '''
    if os.path.isfile(DEFAULT_JAVA):
        return DEFAULT_JAVA
    return java

def get_python(python = "python"):
    '''
    return default python if it exists
    '''
    if os.path.isfile(DEFAULT_PYTHON):
        return DEFAULT_PYTHON
    return python

def count_variants(vcf):
    '''
    count number of variants
    :param vcf:
    :return:
    '''
    count = 0
    with versatile_open(vcf, 'r') as fh:
        for l in fh:
            if l.rstrip() and (not l.startswith('#')):
                count += 1
    return count

def check_java(java="java"):
    logger = logging.getLogger(check_java.__name__)
    try:
        output = subprocess.check_output(f"{java} -Xmx100m -version", stderr=subprocess.STDOUT, shell=True).decode("utf-8")
        logger.debug("Java version output:\n%s", output)

        # Parse version string from any line containing 'version'
        version_line = next((line for line in output.strip().split("\n") if "version" in line),None)
        if not version_line:
            raise EnvironmentError("Could not detect Java version from output:\n" + output)

        jv = version_line.split()[2].strip('"')

        if LooseVersion(jv) < LooseVersion("1.8"):
            logger.error("VarSim requires Java 1.8 or higher.")
            raise EnvironmentError("VarSim requires Java 1.8 or higher")
    except subprocess.CalledProcessError:
        raise EnvironmentError("Java not found or not working properly")


def get_version(java="java"):
    java = get_java(java)
    return subprocess.check_output("{} -jar {} -version".format(java, VARSIMJAR), shell=True).strip()

def run_shell_command(cmd, cmd_stdout, cmd_stderr, cmd_dir="."):
    '''
    run command (list of str or str), redirect stdout, stderr to user-specified file handles
    :param cmd:
    :param cmd_stdout:
    :param cmd_stderr:
    :param cmd_dir:
    :return:
    '''
    logger = logging.getLogger(run_shell_command.__name__)
    if type(cmd) == list:
        cmd = ' '.join(cmd)
    logger.info('running ' + cmd + '\n')
    subproc = subprocess.Popen(cmd, stdout=cmd_stdout, stderr=cmd_stderr, cwd=cmd_dir, shell=True, preexec_fn=os.setsid, close_fds=True)
    logger.info('PID ' + str(subproc.pid) + '\n')
    try:
        retcode = subproc.wait()
    except KeyboardInterrupt:
        logger.warning('receiving SIGINT ...')
        os.killpg(os.getpgid(subproc.pid), signal.SIGINT)
        subproc.wait()
        sys.exit(1)
    if retcode != 0:
        raise Exception('{0} failed'.format(cmd))
    return(retcode)

def makedirs(dirs):
    if type(dirs) == list:
        for d in dirs:
            if not os.path.exists(d):
                os.makedirs(d)
    else:
        if not os.path.exists(dirs):
            os.makedirs(dirs)

def versatile_open(filename, mode):
    '''
    open regular file, gzipped files
    :param filename: filename string
    :param mode: mode string
    :return: file handle
    '''
    if filename.endswith('.gz'):
        import gzip
        return gzip.open(filename, mode)
    else:
        return open(filename, mode)

def check_simulator_opts(simulator, simulator_opts):
    '''
    check opts string for a particular simulator
    :param simulator:
    :param opts:
    :return:
    '''
    #TODO: we need to check if the options are really required
    required_opts = {
        'dwgsim' : ['-e', '-E', '-d', '-s', '-1', '-2'],
        'art' : ['-p','-l','-m','-s'],
        'longislnd' : []
    }
    if simulator:
        if simulator in required_opts:
            for i in required_opts[simulator]:
                if not (i in simulator_opts):
                    raise ValueError('{0} is missing for {1}'.format(i, simulator))
        else:
            raise NotImplementedError("simulator {0} is not supported".format(simulator))
    else:
        return

def get_loglevel(string):
    '''
    take literal loglevel
    return loglevel defined in logging module
    :param string:
    :return:
    '''
    if string == "info":
        return logging.INFO
    if string == "warn":
        return logging.WARN
    if string == "debug":
        return logging.DEBUG
    return logging.INFO

def combine_vcf(combined_vcf, vcfs, duplicate_handling_mode = COMBINE_KEEP_ALL_DUPLICATE, gzip = True):
    '''
    combine multiple VCFs, sort, optionally remove duplicate
    :param combined_vcf:
    :param vcfs:
    :param rm_duplicate: if true, remove duplicate variants (by chr+pos+ref+alt)
    :return: output file name
    '''
    logger = logging.getLogger(combine_vcf.__name__)
    logger.info("Merging {0}".format(" ".join(map(str, vcfs))))
    if not vcfs or len(vcfs) < 2:
        raise ValueError('at least 2 VCFs required')

    sort_command = [SORT_VCF]
    sort_command.extend(vcfs)
    gz_vcf = "{}.gz".format(combined_vcf)
    with open(combined_vcf, "w") as sorted_out:
        run_shell_command(sort_command, cmd_stdout=sorted_out, cmd_stderr=sys.stderr)
    if duplicate_handling_mode == COMBINE_KEEP_FIRST_DUPLICATE or duplicate_handling_mode == COMBINE_KEEP_NO_DUPLICATE:
        previous_line = None
        current_count = 0
        uniq_vcf = combined_vcf + '.uniq'
        with open(combined_vcf, "r") as input, open(uniq_vcf, 'w') as output:
            for l in input:
                if l.startswith('#'):
                    output.write(l)
                elif previous_line:
                    #assume no empty field
                    chr0, pos0, id0, ref0, alt0 = previous_line.rstrip().split()[0:5]
                    chr1, pos1, id1, ref1, alt1 = l.rstrip().split()[0:5]
                    if (chr0, pos0, ref0, alt0) == (chr1, pos1, ref1, alt1):
                        #duplicate
                        current_count += 1
                    else:
                        if duplicate_handling_mode == COMBINE_KEEP_FIRST_DUPLICATE or\
                                (duplicate_handling_mode == COMBINE_KEEP_NO_DUPLICATE and current_count == 1):
                            output.write(previous_line)
                        elif current_count > 1:
                            logger.debug('{0} duplicated {1} times, are discarded'.format(previous_line, current_count))
                        previous_line = l
                        current_count = 1
                else:
                    previous_line = l
                    current_count = 1
            #process last variant record
            if previous_line:
                if duplicate_handling_mode == COMBINE_KEEP_FIRST_DUPLICATE or \
                    (duplicate_handling_mode == COMBINE_KEEP_NO_DUPLICATE and current_count == 1):
                    output.write(previous_line)
        os.rename(uniq_vcf, combined_vcf)
    if gzip:
        run_shell_command([BGZIP, "--force", combined_vcf], cmd_stdout=sys.stdout, cmd_stderr=sys.stderr)
        index_vcf_gz(gz_vcf)
        return gz_vcf
    else:
        return combined_vcf

def index_vcf_gz(vcf_gz):
    pysam.tabix_index(vcf_gz, force = True, preset = 'vcf')

def sort_and_compress(vcf, output_prefix = None, mode = 1, overwrite = False):
    '''
    sort and compress vcf and return compressed filename
    Params:
        vcf: input
        mode: 1 for backward compatibility, 2 for more reasonable behavior,
              3 for saving temp files based on output_prefix
    Returns:
        gzipped vcf filename
    '''
    logger = logging.getLogger(sort_and_compress.__name__)
    if mode == 1:
        gz_vcf = "{}.gz".format(vcf)
        sorted_vcf = "{}.sorted".format(vcf)

        sort_command = [SORT_VCF, vcf]
        with open(sorted_vcf, "w") as sorted_out:
            run_shell_command(sort_command, cmd_stdout=sorted_out, cmd_stderr=sys.stderr)
        os.rename(sorted_vcf, vcf)
        pysam.tabix_index(vcf, force=True, preset='vcf')
        return gz_vcf
    elif mode == 2:
        suffix_index = vcf.rfind('.vcf')
        sorted_vcf = vcf[:suffix_index] + ".sorted" + vcf[suffix_index:]
        gz_vcf = "{}.gz".format(sorted_vcf)

        sort_command = [SORT_VCF, vcf]
        logger.info('sorting {}'.format(vcf))
        if (not overwrite) and os.path.isfile(sorted_vcf):
            raise ValueError("{} exists".format(sorted_vcf))
        with open(sorted_vcf, "w") as sorted_out:
            run_shell_command(sort_command, cmd_stdout=sorted_out, cmd_stderr=sys.stderr)
        logger.info('compressing {}'.format(sorted_vcf))
        if (not overwrite) and os.path.isfile(gz_vcf):
            raise ValueError("{} exists".format(gz_vcf))
        with open(gz_vcf, "w") as out:
            run_shell_command([BGZIP, "--force", "--stdout", sorted_vcf], cmd_stdout=out, cmd_stderr=sys.stderr)
        index_vcf_gz(gz_vcf)
        return gz_vcf
    elif mode == 3:
        if output_prefix is None:
            raise ValueError('Expecting output_prefix for this mode')
        sorted_vcf = output_prefix + ".sorted.vcf"
        gz_vcf = "{}.gz".format(sorted_vcf)

        sort_command = [SORT_VCF, vcf]
        logger.info('sorting {}'.format(vcf))
        if (not overwrite) and os.path.isfile(sorted_vcf):
            raise ValueError("{} exists".format(sorted_vcf))
        with open(sorted_vcf, "w") as sorted_out:
            run_shell_command(sort_command, cmd_stdout=sorted_out, cmd_stderr=sys.stderr)
        logger.info('compressing {}'.format(sorted_vcf))
        if (not overwrite) and os.path.isfile(gz_vcf):
            raise ValueError("{} exists".format(gz_vcf))
        with open(gz_vcf, "w") as out:
            run_shell_command([BGZIP, "--force", sorted_vcf], cmd_stdout=out, cmd_stderr=sys.stderr)
        index_vcf_gz(gz_vcf)
        return gz_vcf
    else:
        raise ValueError

def write_vcf(lines, vcf):
    """Create a file from the provided list"""

    with open(vcf, "w") as vcf_handle:
        vcf_handle.write('\n'.join(lines))
    return vcf


def write_filtered_vcf(vcf, chrm, out_vcf):
    """Extract from a vcf file only variants that are located in a specified chromosome"""

    content = []

    with versatile_open(vcf, "r") as vcf_handle:

        for line in vcf_handle:
            line_strip = line.strip()
            line_split = line_strip.split()

            if line_split[0][0] == "#" or line_split[0] == chrm:
                content.append(line_strip)

    return write_vcf(content, out_vcf)


def get_closest_variant(variant, vcf):
    """Return the variant in a vcf closest to a variant"""

    closest_variant = None

    with versatile_open(vcf, "r") as vcf_handle:
        min_dist = 100

        for line in vcf_handle:
            line_split = str(line).strip().split()

            if line_split[0][0] == "#":
                continue

            if line_split[0] == variant[0]:
                dist = abs(int(line_split[1])-int(variant[1]))

                if dist < min_dist:
                    min_dist = dist
                    closest_variant = line_split[:]

    return closest_variant


def get_matching_alt_ref(variant, vcf):
    """Return the variant in a vcf at the same position with matching alt and ref"""

    matching_alt_ref = None

    with versatile_open(vcf, "r") as vcf_handle:
        for line in vcf_handle:
            line_split = str(line).strip().split()

            if line_split[0][0] == "#":
                continue

            if variant[0] == line_split[0] and variant[1] == line_split[1] and variant[3] == line_split[3] and variant[4] == line_split[4]:
                matching_alt_ref = line_split[:]
                break

    return matching_alt_ref


def get_info(var, entry):
    """Return a value for a user selected field in a line from a vcf (provided as a list split by whitespace)"""

    ret_val = None

    try:
        #Loop through vcf fields backwards
        for field in var[::-1]:
            #First try fields seperated with an ':' e.g. GT:AO	0/1:23
            found = re.search("['\t', ':']{}['\t', ':']".format(entry), field)
            if found:
                field_split = field.split(':')
                entry_index = field_split.index('{}'.format(entry))
                field_index = var.index(field)
                ret_val = var[field_index+1].split(':')[entry_index]
                break

            #Second try fields with an '=' e.g. AO=23;RO=45
            found = re.search("['\t', ';']{}=".format(entry), field)
            if found:
                ret_val = re.split("['\t', ';']{}=".format(entry), field)[1].split(';')[0]
                break
    except:
        pass

    return ret_val


def make_clean_vcf(vcf, path=None):
    """Make a clean vcf retaining essential fields"""
    vcf_path = os.path.split(vcf)

    if vcf_path[1].endswith('.gz'):
        vcf_base = os.path.splitext(os.path.splitext(vcf_path[1])[0])
    else:
        vcf_base = os.path.splitext(vcf_path[1])

    if not path:
        path = vcf_path

    clean_vcf = os.path.join(path, vcf_base[0] + ".clean" + vcf_base[1])

    clean_vcf_handle = open(clean_vcf, "w")

    with versatile_open(vcf, "r") as vcf_handle:
        for line in vcf_handle:
            line_strip = line.strip()
            line_split = line_strip.split()

            if line_strip[0] == "#":
                clean_vcf_handle.write(line_strip+'\n')
                continue
            else:
                GT = "0/1" if line_split[-1] == "./." else line_split[-1]
                if len(line_split) > 7:
                    info_entries = [x.split('=')[0] for x in line_split[7].split(';')]
                    info = "." if len(set(info_entries)) < len(info_entries) else line_split[7]
                else:
                    info = "."
                if len(line_split) >= 9:
                    clean_vcf_handle.write('\t'.join([line_split[0], line_split[1], ".", line_split[3], line_split[4], ".", ".", info, line_split[8], GT]) + '\n')
                else:
                    warnings.warn("line {} has <9 fields".format(line_strip), RuntimeWarning)

    clean_vcf_handle.close()

    clean_vcf = sort_and_compress(clean_vcf)

    return clean_vcf
