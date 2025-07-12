FROM rockylinux:8

ARG branch_of_interest=master
ENV VARSIM_VERSION=$branch_of_interest

# Install system dependencies
RUN yum update -y && \
    yum install -y \
        gcc gcc-c++ make \
        zlib-devel curl less vim bzip2 \
        git wget unzip \
        java-1.8.0-openjdk-devel \
        maven ant \
        python3 python3-pip && \
    yum clean all

# Clone your fixed fork of VarSim
RUN cd /opt && \
    git clone https://github.com/Alx-Kouris/varsim.git

# Use your updated build script
RUN cd /opt/varsim && \
    git checkout ${VARSIM_VERSION} && \
    ./build.sh

# Add VarSim to PATH
ENV PATH="/opt/varsim:$PATH"
