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
import requests
from collections import defaultdict
from flask import Flask
from flask import Response
from flask import abort
from flask import render_template


app = Flask(__name__)

app.config['DEBUG'] = True
app.config['PROXY_ROOT'] = os.environ['PROXY_ROOT']
app.config['DL_BUFFER_SIZE'] = 2 * 1024  # in bytes


def stat():
    return {
        'TOTAL': 0,
        'CACHED': 0,
        'PROXIED': 0
    }


# Stats Holder
stat_data = {
    'TOTAL': 0,
    'CACHED': 0,
    'PROXIED': 0,
    'BY_FILE': defaultdict(stat),  # same stats, but per file
    'BY_CODE': defaultdict(stat)   # same stats, but per code
}


def update_stats(path, cached=False, code=200):
    stat_data['TOTAL'] += 1
    stat_data['BY_FILE'][path]['TOTAL'] += 1
    stat_data['BY_CODE'][code]['TOTAL'] += 1
    if cached:
        stat_data['CACHED'] += 1
        stat_data['BY_FILE'][path]['CACHED'] += 1
        stat_data['BY_CODE'][code]['CACHED'] += 1
    else:
        stat_data['PROXIED'] += 1
        stat_data['BY_FILE'][path]['PROXIED'] += 1
        stat_data['BY_CODE'][path]['PROXIED'] += 1


@app.route("/")
def index():
    return render_template('index.html')


@app.route("/stats")
def stats():
    return render_template('stats.html', stats=stat_data)


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
    app.run()
