#!/usr/bin/env python3

import os
import getpass
import pwd
import grp
from netrc import netrc, NetrcParseError
from pywebhdfs.webhdfs import PyWebHdfsClient
from stat import S_IFDIR, S_IFLNK, S_IFREG
from time import time
import datetime
import configparser
from requests_kerberos import HTTPKerberosAuth

cfg = configparser.ConfigParser()
def write_default_config():
    if not os.path.exists(os.environ['HOME'] + '/.config'):
        os.makedirs(os.environ['HOME'] + '/.config')
    webhdfs_host = input("WebHDFS hostname (without https): ")
    cfg.set('DEFAULT', 'HDFS_HOST', webhdfs_host)
    webhdfs_baseurl_default = "https://{}:8443/gateway/webhdfs/webhdfs/v1/".format(webhdfs_host)
    webhdfs_baseurl = input("HDFS base URL [{}]: ".format(webhdfs_baseurl_default)) or webhdfs_baseurl_default
    cfg.set('DEFAULT', 'HDFS_BASEURL', webhdfs_baseurl)
    if webhdfs_baseurl.lower().startswith('https'):
        webhdfs_cert = input("HDFS web server certificate path [/etc/ssl/certs/ca-certificates.crt]: ") or "/etc/ssl/certs/ca-certificates.crt"
        cfg.set('DEFAULT', 'HDFS_CERT', webhdfs_cert)
    webhdfs_username = input("HDFS username: ")
    cfg.set('DEFAULT', 'HDFS_USERNAME', webhdfs_username)
    webhdfs_password = getpass.getpass(prompt="HDFS password: ")
    cfg.set('DEFAULT', 'HDFS_PASSWORD', webhdfs_password)
    with open(os.environ['HOME'] + '/.config/webhdfs.ini', 'w') as configfile:
        cfg.write(configfile)

if not os.path.exists(os.environ['HOME'] + '/.config/webhdfs.ini'):
    write_default_config()

cfg.read(os.environ['HOME'] + '/.config/webhdfs.ini')

def get_auth():
    return HTTPKerberosAuth()

uid_cache = dict()
def owner_to_uid(owner):
    if owner in uid_cache:
        return uid_cache[owner]
    try:
        uid_cache[owner] = pwd.getpwnam(owner)[2]
        return pwd.getpwnam(owner)[2]
    except KeyError:
        res = pwd.getpwnam('nobody')[2] or 0
        uid_cache[owner] = res
        return res

gid_cache = dict()
def group_to_gid(group):
    if group in gid_cache:
        return gid_cache[group]
    for g in [group, 'nogroup', 'nobody']:
        try:
            gid_cache[group] = grp.getgrnam(g)[2]
            return grp.getgrnam(g)[2]
        except KeyError:
            pass
    gid_cache[group] = 0
    return 0

def webhdfs_connect():
    webhdfs = PyWebHdfsClient(base_uri_pattern=cfg['DEFAULT']['HDFS_BASEURL'],
                              request_extra_opts={'verify': cfg['DEFAULT'].get('HDFS_CERT', None),
                                                  'auth': get_auth()})
    return webhdfs

def webhdfs_entry_to_dict(s):
    mode = int(s['permission'], 8)
    if s['type'] == 'DIRECTORY':
        mode |= S_IFDIR
    else:
        mode |= S_IFREG
    mtime = s['modificationTime'] / 1000
    atime = s['accessTime'] / 1000
    blksize = max(s['blockSize'], 1024*1024)
    sd = dict(name=s['pathSuffix'],
              st_mode=mode,
              st_ctime=mtime,
              st_mtime=mtime,
              st_atime=atime,
              st_nlink=s['childrenNum'] or 1,
              st_blocks=s['length'] // blksize,
              st_size=s['length'],
              st_creator = s['owner'],
              st_uid=owner_to_uid(s['owner']),
              st_gid=group_to_gid(s['group']),
              st_blksize=blksize)
    return sd

if __name__ == '__main__':
    webhdfs = webhdfs_connect()
    now = time()
    for s in webhdfs.list_dir('/')["FileStatuses"]["FileStatus"]:
        sd = webhdfs_entry_to_dict(s)
        print("{:16}\t{:6}\t{:16}\t{:16}\t{}\t{:9}\t{}"
              .format(sd['st_mode'], sd['st_nlink'], sd['st_uid'],
                      sd['st_gid'], sd['st_blocks'],
                      datetime.datetime.fromtimestamp(sd['st_mtime'] / 1000).strftime('%Y-%m-%d %H:%M'),
                      sd['name']))
