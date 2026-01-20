from flask import Flask, request, jsonify, render_template
from engine import GMCScannerEngine
import os
import requests

app = Flask(__name__)
WEBHOOK_URL = os.getenv("GMC_WEBHOOK", "")

@app.route('/')
def index():
    return """<!DOCTYPE html>
<html lang='en'>
<head>
    <meta charset='UTF-8'><title>GMC Guardian Pro</title>
    <script src='https://cdn.tailwindcss.com'></script>
    <link href='https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css' rel='stylesheet'>
</head>
<body class='bg-gray-900 text-white min-h-screen font-sans'>
    <div class='max-w-6xl mx-auto p-8'>
        <header class='flex justify-between items-center mb-12'>
            <h1 class='text-3xl font-black tracking-tighter text-indigo-400'><i class='fas fa-shield-halved mr-2'></i>GMC GUARDIAN</h1>
            <div class='text-sm text-gray-400'>v3.0 Enterprise Edition</div>
        </header>

        <div class='bg-gray-800 rounded-3xl p-10 shadow-2xl border border-gray-700'>
            <div class='max-w-2xl mx-auto text-center mb-10'>
                <h2 class='text-4xl font-bold mb-4'>Audit Your Compliance</h2>
                <p class='text-gray-400'>Deep-scan your store for Google Merchant Center policy violations.</p>
            </div>

            <div class='flex gap-4 mb-12'>
                <input type='text' id='url' placeholder='https://your-store.com' class='flex-1 bg-gray-700 border-none rounded-2xl p-5 text-lg focus:ring-2 focus:ring-indigo-500 outline-none'>
                <button onclick='runAudit()' id='btn' class='bg-indigo-600 hover:bg-indigo-500 px-10 py-5 rounded-2xl font-bold transition-all transform hover:scale-105'>Analyze Now</button>
            </div>

            <div id='loader' class='hidden py-20 text-center'>
                <div class='inline-block animate-spin w-12 h-12 border-4 border-indigo-500 border-t-transparent rounded-full mb-4'></div>
                <p class='text-indigo-400 font-medium'>Crawling deep-links & analyzing text...</p>
            </div>

            <div id='results' class='hidden space-y-8'>
                <div class='flex items-center justify-between bg-gray-700/50 p-8 rounded-3xl'>
                    <div>
                        <h3 id='resDomain' class='text-2xl font-bold'></h3>
                        <p class='text-gray-400'>Full Compliance Report</p>
                    </div>
                    <div class='text-right'>
                        <div id='resScore' class='text-6xl font-black text-indigo-400'></div>
                        <div class='text-xs uppercase tracking-widest text-gray-500 mt-1'>Health Score</div>
                    </div>
                </div>

                <div class='overflow-hidden rounded-2xl border border-gray-700'>
                    <table class='w-full text-left'>
                        <thead class='bg-gray-700 text-gray-300 text-sm uppercase'>
                            <tr><th class='p-5'>Page Type</th><th class='p-5'>URL</th><th class='p-5'>Status</th><th class='p-5'>Details</th></tr>
                        </thead>
                        <tbody id='tableBody' class='divide-y divide-gray-700'></tbody>
                    </table>
                </div>
                
                <div class='flex justify-center gap-4'>
                    <button onclick='window.print()' class='bg-gray-700 hover:bg-gray-600 px-8 py-3 rounded-xl font-bold transition'><i class='fas fa-file-pdf mr-2'></i>Save PDF</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        async function runAudit() {
            const url = document.getElementById('url').value;
            if(!url) return;
            const btn = document.getElementById('btn');
            const loader = document.getElementById('loader');
            const results = document.getElementById('results');

            btn.disabled = true; loader.classList.remove('hidden'); results.classList.add('hidden');

            try {
                const res = await fetch('/audit?url=' + encodeURIComponent(url));
                const data = await res.json();
                
                document.getElementById('resDomain').innerText = data.domain;
                document.getElementById('resScore').innerText = data.score + '%';
                
                document.getElementById('tableBody').innerHTML = data.rows.map(r => `
                    <tr class='hover:bg-gray-700/30 transition'>
                        <td class='p-5 font-bold text-indigo-300'>${r.type}</td>
                        <td class='p-5 text-xs text-gray-400 truncate max-w-xs'>${r.url}</td>
                        <td class='p-5'><span class='px-3 py-1 rounded-full text-xs font-black ${r.status === 'Pass' ? 'bg-green-900/50 text-green-400' : 'bg-red-900/50 text-red-400'}'>${r.status}</span></td>
                        <td class='p-5 text-xs text-gray-300'>${r.details}</td>
                    </tr>
                `).join('');

                results.classList.remove('hidden');
            } catch (e) { alert('Audit failed.'); }
            finally { btn.disabled = false; loader.classList.add('hidden'); }
        }
    </script>
</body>
</html>"""

@app.route('/audit')
def audit():
    url = request.args.get('url')
    engine = GMCScannerEngine(url)
    report = engine.scan()
    
    if WEBHOOK_URL and "rows" in report:
        for row in report["rows"]:
            try: requests.post(WEBHOOK_URL, json={"domain": report["domain"], **row}, timeout=2)
            except: pass
            
    return jsonify(report)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
