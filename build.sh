#!/usr/bin/env bash

set -ex

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
OPT_DIR=${DIR}/opt

mkdir -p ${OPT_DIR}
pushd ${OPT_DIR}

PYTHON_DIR=${OPT_DIR}/miniconda2
CONDA=Miniconda2-4.6.14-Linux-x86_64.sh
samtools_version="1.9"
SAMTOOLS_DIR=${OPT_DIR}/samtools-${samtools_version}_install
HTSLIB_DIR=${OPT_DIR}/htslib-1.9_install

if [[ ! -d ${PYTHON_DIR} ]]; then
wget --no-check-certificate -q https://repo.continuum.io/miniconda/${CONDA}\
    && sh ${CONDA} -b -p ${PYTHON_DIR}\
    && ${PYTHON_DIR}/bin/python ${PYTHON_DIR}/bin/pip install pysam==0.15.0\
    && ${PYTHON_DIR}/bin/python ${PYTHON_DIR}/bin/pip install pyvcf==0.6.8\
    && ${PYTHON_DIR}/bin/python ${PYTHON_DIR}/bin/conda install --yes -c bioconda pybedtools=0.8.0 bedtools=2.25.0 \
    && ${PYTHON_DIR}/bin/python ${PYTHON_DIR}/bin/pip install scipy==1.1.0\
    && ${PYTHON_DIR}/bin/python ${PYTHON_DIR}/bin/conda install --yes -c bioconda samtools=${samtools_version} htslib=1.9\
    && rm -f ${CONDA}

    if [[ ! -d $SAMTOOLS_DIR ]]; then
        mkdir -p ${SAMTOOLS_DIR}/bin/
        for i in samtools bgzip tabix;do
            ln -sf ${PYTHON_DIR}/bin/${i} ${SAMTOOLS_DIR}/bin/
        done
    fi

    if [[ ! -d $HTSLIB_DIR ]]; then
        mkdir -p ${HTSLIB_DIR}/bin/
        for i in bgzip htsfile tabix;do
            ln -sf ${PYTHON_DIR}/bin/${i} ${HTSLIB_DIR}/bin/
        done
    fi
fi

BZIP_DIR=${OPT_DIR}/bzip2-1.0.6
if [[ ! -d ${BZIP_DIR} ]]; then
    wget --no-check-certificate -O- https://www.sourceware.org/pub/bzip2/bzip2-1.0.6.tar.gz --no-check-certificate | tar zxvf -
    pushd ${BZIP_DIR}
    make install PREFIX=${BZIP_DIR}_install CFLAGS=" -fPIC"
    popd
fi

# Download ART
ART_DIR=${OPT_DIR}/ART
if [[ ! -d ${ART_DIR} ]]; then
    mkdir -p ${ART_DIR}
    pushd ${ART_DIR}
    wget --no-check-certificate -O- https://github.com/bioinform/varsim/files/4156868/art_bin_VanillaIceCream.zip > art_bin_VanillaIceCream.zip
    unzip art_bin_VanillaIceCream.zip && rm -f art_bin_VanillaIceCream.zip
    popd
fi

popd

version=$(git describe | sed 's/^v//')
mvn versions:set -DgenerateBackupPoms=false -DnewVersion=$version
mvn package

git submodule init
git submodule update
pushd rtg-tools
rm -rf rtg-tools-*
ant zip-nojre
unzip dist/rtg-tools*.zip
cp rtg-tools*/RTG.jar $DIR
popd
