const $=id=>document.getElementById(id);
const base=(window.FMIS_API_BASE||"").trim().replace(/\/$/,"");
const now=new Date();
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
    $("uploadMsg").textContent=(r.storage==="cloudflare_kv"?"Saved permanently to Cloudflare KV: ":"Validated and loaded ")+r.loaded+" rows.";
    await health();
  }catch(e){$("uploadMsg").textContent=e.message;}
};
$("analyze").onclick=async()=>{
  try{
    const r=await request("/api/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({home_team:$("home").value,away_team:$("away").value,as_of:$("date").value,total_line:Number($("total").value),handicap_home:Number($("handicap").value)})});
    $("result").textContent=JSON.stringify(r,null,2);
  }catch(e){$("result").textContent=e.message;}
};
health();
