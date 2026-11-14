const $=id=>document.getElementById(id);
const base=(window.FMIS_API_BASE||"").trim().replace(/\/$/,"");
const now=new Date();
let lastPrediction=null;
if(!$("date").value){
  const localDate=new Date(now.getTime()-now.getTimezoneOffset()*60000);
  $("date").value=localDate.toISOString().slice(0,10);
}
async function request(path,options={}){
  if(!base) throw new Error("Backend belum dikonfigurasi. Deploy backend FMIS, lalu isi frontend/config.js dengan URL API (contoh: https://nama-service.onrender.com).");
  const r=await fetch(base+path,options);
  const type=r.headers.get("content-type")||"";
  if(!type.includes("application/json")){
    const body=(await r.text()).slice(0,160).replace(/\s+/g," ");
    throw new Error("Backend mengirim respons bukan JSON (HTTP "+r.status+"). Periksa URL backend. Respons: "+body);
  }
  const data=await r.json();
  if(!r.ok) throw new Error(data.detail||"Request failed (HTTP "+r.status+")");
  return data;
}
async function health(){
  try{
    const h=await request("/api/health");
    const savedAt=h.dataset_updated_at? " · saved "+new Date(h.dataset_updated_at).toLocaleString():"";
    $("status").textContent="API online · "+h.matches_loaded+" rows"+savedAt;
  }catch(e){
    $("status").textContent=base?"API offline · "+e.message:"API offline · isi URL backend di config.js";
  }
}
$("upload").onclick=async()=>{
  const f=$("csv").files[0];
  if(!f) return $("uploadMsg").textContent="Choose a CSV file first.";
  const body=new FormData();
  body.append("file",f);
  try{
    const r=await request("/api/data/csv",{method:"POST",headers:{"X-Admin-Token":$("adminToken").value},body});
    $("uploadMsg").textContent=(r.storage==="cloudflare_kv"?"Saved to Cloudflare KV: ":"Validated and loaded ")+r.loaded+" rows.";
    await health();
  }catch(e){$("uploadMsg").textContent=e.message;}
};
$("analyze").onclick=async()=>{
  try{
    const fixture={home_team:$("home").value.trim(),away_team:$("away").value.trim(),as_of:$("date").value};
    const r=await request("/api/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({...fixture,total_line:Number($("total").value),handicap_home:Number($("handicap").value)})});
    const prediction=r.prediction||r;
    lastPrediction={fixture,prediction,data_quality:r.data_quality||null};
    $("savePrediction").disabled=false;
    $("result").textContent=JSON.stringify(r,null,2);
  }catch(e){$("result").textContent=e.message;}
};
$("savePrediction").onclick=async()=>{
  if(!lastPrediction) return;
  try{
    const r=await request("/api/predictions",{method:"POST",headers:{"Content-Type":"application/json","X-Admin-Token":$("adminToken").value},body:JSON.stringify(lastPrediction)});
    $("resultId").value=r.prediction.id;
    $("trackerMsg").textContent="Prediction saved. ID: "+r.prediction.id;
    await refreshTracker();
  }catch(e){$("trackerMsg").textContent=e.message;}
};
async function refreshTracker(){
  try{
    const [list,metrics]=await Promise.all([request("/api/predictions"),request("/api/tracker/metrics")]);
    $("trackerMetrics").textContent=JSON.stringify(metrics,null,2);
    $("trackerList").textContent=list.predictions.length?list.predictions.map(p=>
      p.status.toUpperCase()+" · "+p.fixture.home_team+" vs "+p.fixture.away_team+" · "+p.fixture.as_of+"\nID: "+p.id+
      (p.actual?"\nActual: "+p.actual.home_goals+"-"+p.actual.away_goals:"")
    ).join("\n\n"):"No saved predictions yet.";
  }catch(e){$("trackerMsg").textContent=e.message;}
}
$("refreshTracker").onclick=refreshTracker;
$("submitResult").onclick=async()=>{
  const id=$("resultId").value.trim();
  const home=Number($("actualHome").value), away=Number($("actualAway").value);
  if(!id) return $("trackerMsg").textContent="Enter a prediction ID.";
  if(!Number.isInteger(home)||!Number.isInteger(away)||home<0||away<0||home>30||away>30)
    return $("trackerMsg").textContent="Enter valid whole-number scores from 0 to 30.";
  try{
    const r=await request("/api/predictions/"+encodeURIComponent(id)+"/result",{method:"POST",headers:{"Content-Type":"application/json","X-Admin-Token":$("adminToken").value},body:JSON.stringify({home_goals:home,away_goals:away})});
    $("trackerMsg").textContent="Actual result saved for "+r.prediction.fixture.home_team+" vs "+r.prediction.fixture.away_team+".";
    await refreshTracker();
  }catch(e){$("trackerMsg").textContent=e.message;}
};
health();
