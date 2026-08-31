import React, {useState} from 'react'

export default function App(){
  const [file, setFile] = useState(null)
  const [uploadResp, setUploadResp] = useState(null)
  const [params, setParams] = useState({
    base_length:224, base_width:90, base_thickness:10, big_cyl_outer_dia:56, big_cyl_inner_dia:35
  })
  const [stepPath, setStepPath] = useState(null)

  async function upload(){
    if(!file) return alert('choose file')
    const fd = new FormData(); fd.append('file', file)
    const r = await fetch('http://localhost:8000/upload_and_detect', {method:'POST', body: fd})
    const j = await r.json()
    setUploadResp(j)
    // apply candidate values if present
    if(j.candidates){
      const np = {...params}
      j.candidates.forEach(c=>{ if(c.name) np[c.name]=c.value })
      setParams(np)
    }
  }

  async function generate(){
    const r = await fetch('http://localhost:8000/generate_model',{method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(params)})
    const j = await r.json()
    setStepPath(j.step)
    alert('STEP generated: ' + j.step)
  }

  async function openNx(){
    if(!stepPath) return alert('no step')
    const r = await fetch('http://localhost:8000/open_nx', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({step_path: stepPath})})
    const j = await r.json()
    alert(JSON.stringify(j))
  }

  return (<div className="max-w-6xl mx-auto p-6">
    <header className="flex items-center justify-between mb-6">
      <h1 className="text-2xl font-semibold">CAD Workbench Demo</h1>
      <div className="text-sm text-slate-500">Demo: upload → detect → generate STEP → open NX</div>
    </header>

    <div className="grid grid-cols-3 gap-4">
      <div className="col-span-1 bg-white p-4 rounded shadow">
        <h2 className="font-medium mb-2">Upload</h2>
        <input type="file" onChange={e=>setFile(e.target.files[0])} />
        <div className="mt-3 flex gap-2">
          <button className="px-3 py-2 bg-blue-600 text-white rounded" onClick={upload}>Upload & Detect</button>
        </div>
        {uploadResp && <div className="mt-3 text-xs text-slate-600">Uploaded: {uploadResp.uploaded}</div>}
      </div>

      <div className="col-span-1 bg-white p-4 rounded shadow">
        <h2 className="font-medium mb-2">Parameters</h2>
        <div className="space-y-2">
          {Object.keys(params).map(k=> (
            <div key={k} className="flex items-center gap-2">
              <label className="w-40 text-sm text-slate-600">{k}</label>
              <input className="border rounded px-2 py-1 w-full" value={params[k]} onChange={e=>setParams({...params, [k]: parseFloat(e.target.value)})} />
            </div>
          ))}
        </div>
        <div className="mt-4 flex gap-2">
          <button className="px-3 py-2 bg-green-600 text-white rounded" onClick={generate}>Generate STEP</button>
          <button className="px-3 py-2 border rounded" onClick={()=>{window.open('http://localhost:8000')}}>API</button>
        </div>
      </div>

      <div className="col-span-1 bg-white p-4 rounded shadow">
        <h2 className="font-medium mb-2">Actions / Output</h2>
        <div className="mb-2 text-sm">STEP: {stepPath ? <span className="text-xs text-slate-700 break-words">{stepPath}</span> : <span className="text-xs text-slate-400">(none)</span>}</div>
        <div className="flex gap-2">
          <button className="px-3 py-2 bg-indigo-600 text-white rounded" onClick={openNx}>Open in NX</button>
        </div>
      </div>
    </div>

  </div>)
}
