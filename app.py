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
from flask import Flask
from flask import Response
from flask import abort
from flask import render_template

app = Flask(__name__)

app.config['DEBUG'] = True
app.config['PROXY_ROOT'] = os.environ['PROXY_ROOT']
app.config['DL_BUFFER_SIZE'] = 2 * 1024  # in bytes

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/files/<path:path>")
def files(path):
    full_path = osp.abspath(osp.join(app.static_folder, path))
    if osp.exists(full_path):
        if osp.isfile(full_path):
            return app.send_static_file(path)
        elif osp.isdir(full_path):
            return "Directory Index"
    else:
        # make local directory for the file
        root_dir = osp.dirname(full_path)
        if not osp.exists(root_dir):
            os.makedirs(root_dir)
        # request from proxy'd server
        r = requests.get(osp.join(app.config['PROXY_ROOT'], path), stream=True)
        # if request is OK, stream it and save to disk, otherwise fail
        if r.status_code == 200:
            def generate():
                with open(full_path, 'wb') as fd:
                    for chunk in r.iter_content(app.config['DL_BUFFER_SIZE']):
                        fd.write(chunk)
                        yield chunk
            return Response(generate(), mimetype='application/octet-stream')
        else:
            abort(r.status_code)

if __name__ == "__main__":
    app.run()
