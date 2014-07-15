#!/usr/bin/env python
#
# A simply static file proxy
#  - looks for files locally...
#     if file exists, it serves it
#     if not, it downloads it and saves a copy
#  - once downloaded the file will exist forever
#
import os
import os.path as osp
import json
import requests
import hashlib
from flask import Flask
from flask import Response
from flask import abort
from flask import render_template
from flask_redis import Redis


class RedisStats(object):
    def __init__(self, redis, key):
        self.r = redis
        self.key = key
        self.hsh = hashlib.sha1(key).hexdigest()

    def incr(self, tag):
        return self.r.hincrby(self.hsh, tag, 1)

    def reset(self, tag):
        self.r.hset(self.hsh, tag, 0)

    def __getitem__(self, index):
        val = self.r.hget(self.hsh, index)
        return (val) and val or 0


class RedisTop10(object):
    def __init__(self, redis, key):
        self.r = redis
        self.key = key
        self.hsh = hashlib.sha1(key).hexdigest()

    def incr(self, tag):
        self.r.zincrby(self.hsh, tag, 1.0)

    def reset(self, tag):
        self.r.zrem(self.hsh, tag)

    def __iter__(self):
        return iter(self.r.zrevrange(self.hsh, 0, 9, withscores=True))

    def __nonzero__(self):
        return self.r.zcard(self.hsh)


app = Flask(__name__)

app.config['DEBUG'] = True
app.config['PROXY_ROOT'] = os.environ['PROXY_ROOT']
app.config['DL_BUFFER_SIZE'] = 2 * 1024  # in bytes

# Setup Redis for stats
cf_cfg = json.loads(os.environ.get('VCAP_SERVICES', '{}'))
if cf_cfg:
    creds = cf_cfg.get('rediscloud', {}).get('credentials')
    app.config['REDIS_HOST'] = creds['hostname']
    app.config['REDIS_PASSWORD'] = creds['password']
    app.config['REDIS_PORT'] = creds['port']
else:
    app.config['REDIS_HOST'] = 'localhost'
    app.config['REDIS_PORT'] = 6379
    app.config['REDIS_PASSWORD'] = ''
redis_store = Redis(app)


# Stats collections, backed by Redis
stat_total = RedisStats(redis_store, 'total')
stat_files = RedisTop10(redis_store, 'top10Files')
stat_codes = RedisTop10(redis_store, 'top10Codes')
stat_cached = RedisTop10(redis_store, 'top10Cached')
stat_proxied = RedisTop10(redis_store, 'top10Proxied')


def update_stats(path, cached=False, code=200):
    stat_total.incr('TOTAL')
    stat_files.incr(path)
    stat_codes.incr(code)
    if cached:
        stat_total.incr('CACHED')
        stat_cached.incr(path)
    else:
        total = stat_total.incr('PROXIED')
        stat_proxied.incr(path)


@app.route("/")
def index():
    return render_template('index.html')


@app.route("/stats")
def stats():
    return render_template('stats.html',
                           stat_total=stat_total,
                           stat_files=stat_files,
                           stat_codes=stat_codes,
                           stat_cached=stat_cached,
                           stat_proxied=stat_proxied)


@app.route("/browse", defaults={'path': None})
@app.route("/browse/<path:path>")
def browse(path):
    return render_template('browse.html')


@app.route("/files/<path:path>")
def files(path):
    full_path = osp.abspath(osp.join(app.static_folder, 'files', path))
    if osp.exists(full_path):
        if osp.isfile(full_path):
            update_stats(path, cached=True)
            return app.send_static_file(osp.join('files', path))
        elif osp.isdir(full_path):
            return "Directory Index"  # redirect to browse
    else:
        # make local directory for the file
        root_dir = osp.dirname(full_path)
        if not osp.exists(root_dir):
            os.makedirs(root_dir)
        # request from proxy'd server
        r = requests.get(osp.join(app.config['PROXY_ROOT'], path), stream=True)
        # if request is OK, stream it and save to disk, otherwise fail
        if r.status_code == 200:
            update_stats(path, cached=False)

            def generate():
                with open(full_path, 'wb') as fd:
                    for chunk in r.iter_content(app.config['DL_BUFFER_SIZE']):
                        fd.write(chunk)
                        yield chunk
            return Response(generate(), mimetype='application/octet-stream')
        else:
            update_stats(path, cached=False, code=r.status_code)
            abort(r.status_code)


if __name__ == "__main__":
    app.run(host="0.0.0.0")
