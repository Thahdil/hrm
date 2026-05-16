FROM public.ecr.aws/lambda/python:3.11

RUN yum install -y \
    gcc \
    gcc-c++ \
    make \
    curl \
    tar \
    gzip \
    unixODBC \
    unixODBC-devel \
    yum-utils \
    && yum clean all

WORKDIR /tmp

# Microsoft repo
RUN curl -sSL https://packages.microsoft.com/config/rhel/7/prod.repo \
    -o /etc/yum.repos.d/mssql-release.repo

# Disable GPG checks
RUN sed -i 's/gpgcheck=1/gpgcheck=0/g' \
    /etc/yum.repos.d/mssql-release.repo

# Download RPM package
RUN yumdownloader msodbcsql18 --destdir=/tmp

# Extract RPM manually instead of installing
RUN mkdir -p /opt/microsoft && \
    cd /opt/microsoft && \
    rpm2cpio /tmp/msodbcsql18*.rpm | cpio -idmv

# Verify files
RUN find /opt/microsoft -name "libmsodbcsql*" || true

# Detect actual library path
RUN DRIVER_PATH=$(find /opt/microsoft -name "libmsodbcsql-*.so*" | head -n 1) && \
    echo "Detected Driver: $DRIVER_PATH" && \
    printf "%s\n" \
    "[ODBC Driver 18 for SQL Server]" \
    "Description=Microsoft ODBC Driver 18 for SQL Server" \
    "Driver=$DRIVER_PATH" \
    "UsageCount=1" \
    > /etc/odbcinst.ini

RUN cat /etc/odbcinst.ini

RUN odbcinst -q -d

ENV ODBCSYSINI=/etc
ENV ODBCINI=/etc/odbc.ini

# Important
ENV LD_LIBRARY_PATH=/opt/microsoft/opt/microsoft/msodbcsql18/lib64:${LD_LIBRARY_PATH}

WORKDIR ${LAMBDA_TASK_ROOT}

COPY requirements.txt .

RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

COPY src/ .

ENV PYODBC_DISABLE_POOLING=1

RUN DJANGO_SETTINGS_MODULE=config.settings \
    python manage.py collectstatic --noinput

CMD ["handler.lambda_handler"]