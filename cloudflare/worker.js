const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-Admin-Token",
  "Access-Control-Max-Age": "86400"
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...cors, "Content-Type": "application/json; charset=utf-8" }
  });
}
function fail(detail, status = 400) { return json({ detail }, status); }

function parseCsv(input) {
  const rows = [];
  let row = [], cell = "", quoted = false;
  for (let i = 0; i < input.length; i++) {
    const c = input[i];
    if (quoted) {
      if (c === '"' && input[i + 1] === '"') { cell += '"'; i++; }
      else if (c === '"') quoted = false;
      else cell += c;
    } else if (c === '"' && cell.length === 0) quoted = true;
    else if (c === ",") { row.push(cell); cell = ""; }
    else if (c === "\n") { row.push(cell.replace(/\r$/, "")); rows.push(row); row = []; cell = ""; }
    else cell += c;
  }
  if (quoted) throw new Error("CSV contains an unterminated quoted field");
  if (cell.length || row.length) { row.push(cell.replace(/\r$/, "")); rows.push(row); }
  const nonempty = rows.filter(r => r.some(v => String(v).trim() !== ""));
  if (nonempty.length < 2) throw new Error("CSV must contain a header and at least one match");
  const headers = nonempty[0].map(v => v.trim().replace(/^\uFEFF/, ""));
  if (new Set(headers).size !== headers.length) throw new Error("CSV contains duplicate column names");
  const required = ["date", "home_team", "away_team", "home_goals", "away_goals"];
  const missing = required.filter(k => !headers.includes(k));
  if (missing.length) throw new Error("Missing required columns: " + missing.join(", "));
  const matches = nonempty.slice(1).map((cells, index) => {
    if (cells.length !== headers.length) throw new Error("CSV row " + (index + 2) + " has " + cells.length + " cells; expected " + headers.length);
    const raw = Object.fromEntries(headers.map((h, i) => [h, (cells[i] ?? "").trim()]));
    if (!/^\d{4}-\d{2}-\d{2}$/.test(raw.date) || Number.isNaN(Date.parse(raw.date + "T00:00:00Z"))) throw new Error("Invalid date on CSV row " + (index + 2));
    if (!raw.home_team || !raw.away_team || raw.home_team === raw.away_team) throw new Error("Invalid team names on CSV row " + (index + 2));
    const num = (key, integer = false, optional = false) => {
      if (optional && (raw[key] === undefined || raw[key] === "")) return null;
      if (raw[key] === undefined || raw[key] === "") throw new Error("Missing " + key + " on CSV row " + (index + 2));
      const n = Number(raw[key]);
      if (!Number.isFinite(n) || n < 0 || (integer && !Number.isInteger(n))) throw new Error("Invalid " + key + " on CSV row " + (index + 2));
      return n;
    };
    const m = {
      date: raw.date, home_team: raw.home_team, away_team: raw.away_team,
      home_goals: num("home_goals", true), away_goals: num("away_goals", true)
    };
    if (headers.includes("home_xg")) m.home_xg = num("home_xg", false, true);
    if (headers.includes("away_xg")) m.away_xg = num("away_xg", false, true);
    if (headers.includes("competition")) m.competition = raw.competition;
    return m;
  });
  return { matches, columns: headers };
}

function mean(values) { return values.reduce((a, b) => a + b, 0) / values.length; }
function estimateLambdas(matches, home, away) {
  if (!home.trim() || !away.trim() || home.trim().toLowerCase() === away.trim().toLowerCase()) throw new Error("Home and away teams must be different non-empty names");
  const homeRows = matches.filter(m => m.home_team === home || m.away_team === home);
  const awayRows = matches.filter(m => m.home_team === away || m.away_team === away);
  if (homeRows.length < 3 || awayRows.length < 3) throw new Error("At least 3 prior matches per team are required");
  function scoredConceded(rows, team) {
    const scored = [], conceded = [];
    for (const m of rows) {
      const isHome = m.home_team === team;
      const ownXg = isHome ? m.home_xg : m.away_xg;
      const oppXg = isHome ? m.away_xg : m.home_xg;
      const ownGoals = isHome ? m.home_goals : m.away_goals;
      const oppGoals = isHome ? m.away_goals : m.home_goals;
      scored.push(ownXg == null ? ownGoals : ownXg);
      conceded.push(oppXg == null ? oppGoals : oppXg);
    }
    return [mean(scored), mean(conceded)];
  }
  const [hFor, hAgainst] = scoredConceded(homeRows, home);
  const [aFor, aAgainst] = scoredConceded(awayRows, away);
  const lh = Math.max(0.15, Math.min(4, 0.55 * hFor + 0.45 * aAgainst + 0.12));
  const la = Math.max(0.15, Math.min(4, 0.55 * aFor + 0.45 * hAgainst));
  const usedXg = [...homeRows, ...awayRows].some(m => m.home_xg != null || m.away_xg != null);
  return [lh, la, usedXg ? "mixed_xg_and_goals" : "goals_only"];
}
function poisson(k, lambda) {
  let f = 1;
  for (let i = 2; i <= k; i++) f *= i;
  return Math.exp(-lambda) * Math.pow(lambda, k) / f;
}
function scoreMatrix(lh, la) {
  if (!(lh > 0 && lh <= 8 && la > 0 && la <= 8)) throw new Error("Lambda values must be in (0, 8]");
  const n = 11, matrix = [];
  const ph = Array.from({ length: n }, (_, i) => poisson(i, lh));
  const pa = Array.from({ length: n }, (_, i) => poisson(i, la));
  for (let h = 0; h < n; h++) {
    matrix[h] = [];
    for (let a = 0; a < n; a++) matrix[h][a] = ph[h] * pa[a];
  }
  const rho = -0.08;
  matrix[0][0] *= Math.max(0, 1 - lh * la * rho);
  matrix[0][1] *= Math.max(0, 1 + lh * rho);
  matrix[1][0] *= Math.max(0, 1 + la * rho);
  matrix[1][1] *= Math.max(0, 1 - rho);
  const sum = matrix.flat().reduce((a, b) => a + b, 0);
  return matrix.map(row => row.map(v => v / sum));
}
const settlementKeys = ["win_full", "win_half", "push", "lose_half", "lose_full"];
function settle(v) { return v > 1e-9 ? "win_full" : v < -1e-9 ? "lose_full" : "push"; }
function lineSettlement(distribution, line, over = true) {
  if (Math.abs(line * 4 - Math.round(line * 4)) > 1e-8) throw new Error("Totals and handicap lines must use quarter-goal increments");
  const parts = Math.round(line * 4) % 2 ? [line - 0.25, line + 0.25] : [line];
  const result = Object.fromEntries(settlementKeys.map(k => [k, 0]));
  for (const [goals, probability] of distribution) {
    const outcomes = parts.map(part => settle(over ? goals - part : part - goals));
    if (outcomes.length === 1 || outcomes[0] === outcomes[1]) result[outcomes[0]] += probability;
    else if (outcomes.includes("push")) result[outcomes.includes("win_full") ? "win_half" : "lose_half"] += probability;
    else throw new Error("Unexpected quarter-line settlement state");
  }
  return result;
}
function handicapSettlement(matrix, line) {
  if (Math.abs(line * 4 - Math.round(line * 4)) > 1e-8) throw new Error("Handicap must use quarter-goal increments");
  const parts = Math.round(line * 4) % 2 ? [line - 0.25, line + 0.25] : [line];
  const result = Object.fromEntries(settlementKeys.map(k => [k, 0]));
  for (let h = 0; h < matrix.length; h++) for (let a = 0; a < matrix.length; a++) {
    const outcomes = parts.map(part => settle((h - a) + part));
    const p = matrix[h][a];
    if (outcomes.length === 1 || outcomes[0] === outcomes[1]) result[outcomes[0]] += p;
    else if (outcomes.includes("push")) result[outcomes.includes("win_full") ? "win_half" : "lose_half"] += p;
    else throw new Error("Unexpected quarter-handicap settlement state");
  }
  return result;
}
function predict(lh, la, totalLine, handicapHome) {
  const matrix = scoreMatrix(lh, la);
  let home = 0, draw = 0, away = 0;
  const totals = [];
  for (let h = 0; h < matrix.length; h++) for (let a = 0; a < matrix.length; a++) {
    const p = matrix[h][a];
    if (h > a) home += p; else if (h === a) draw += p; else away += p;
    totals.push([h + a, p]);
  }
  const scores = [];
  for (let h = 0; h < matrix.length; h++) for (let a = 0; a < matrix.length; a++) scores.push({ score: h + "-" + a, probability: matrix[h][a], h, a });
  scores.sort((x, y) => y.probability - x.probability || x.h - y.h || x.a - y.a);
  return {
    expected_goals: { home: lh, away: la },
    most_likely_scores: scores.slice(0, 5).map(({ score, probability }) => ({ score, probability })),
    markets: {
      "1x2": { home, draw, away },
      totals: { line: totalLine, over: lineSettlement(totals, totalLine, true), under: lineSettlement(totals, totalLine, false) },
      asian_handicap_home: { line: handicapHome, ...handicapSettlement(matrix, handicapHome) }
    },
    model: "poisson_dixon_coles"
  };
}
function explain(home, away, prediction, dataQuality) {
  const p = prediction.markets["1x2"];
  const top = Object.keys(p).reduce((a, b) => p[a] >= p[b] ? a : b);
  const labels = { home, draw: "Draw", away };
  const totals = prediction.markets.totals, over = totals.over;
  const pct = n => (n * 100).toFixed(1) + "%";
  const notes = [
    "Highest modeled 1X2 outcome: " + labels[top] + " (" + pct(p[top]) + ").",
    "Most likely exact score in the modeled score grid: " + prediction.most_likely_scores[0].score + ".",
    "Expected goals: " + prediction.expected_goals.home.toFixed(2) + "–" + prediction.expected_goals.away.toFixed(2) + ".",
    "Over " + totals.line + " full/half-win probability: " + pct(over.win_full + over.win_half) + "; push: " + pct(over.push) + ".",
    "Data basis: " + dataQuality + ".",
    "These are model estimates, not guarantees; sparse history, lineups and data coverage can materially change them."
  ];
  if (Math.max(...Object.values(p)) < 0.45) notes.push("No 1X2 outcome dominates the model; uncertainty is relatively high.");
  return { headline: home + " vs " + away + ": " + labels[top] + " is the most likely 1X2 outcome", explanations: notes, decision: "ANALYSIS_ONLY" };
}

async function listPredictions(kv) {
  const records = [];
  let cursor;
  do {
    const page = await kv.list({ prefix: "prediction:", limit: 1000, ...(cursor ? { cursor } : {}) });
    const values = await Promise.all(page.keys.map(async item => {
      const value = await kv.get(item.name, "json");
      return value;
    }));
    records.push(...values.filter(Boolean));
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor && records.length < 10000);
  return records;
}
function validScore(value) {
  return Number.isInteger(value) && value >= 0 && value <= 30;
}
function outcomeFor(homeGoals, awayGoals) {
  return homeGoals > awayGoals ? "home" : homeGoals < awayGoals ? "away" : "draw";
}
function trackerMetrics(records) {
  const settled = records.filter(r => r.status === "settled" && r.actual && r.probabilities);
  const total = records.length;
  if (!settled.length) return { total, pending: total, settled: 0, accuracy: null, brier_score: null, log_loss: null, calibration: [] };
  let correct = 0, brier = 0, logLoss = 0;
  const bins = Array.from({ length: 10 }, (_, i) => ({ bin: i, count: 0, confidence_sum: 0, accuracy_sum: 0 }));
  for (const record of settled) {
    const probs = record.probabilities;
    const actual = outcomeFor(record.actual.home_goals, record.actual.away_goals);
    const keys = ["home", "draw", "away"];
    const predicted = keys.reduce((a, b) => probs[a] >= probs[b] ? a : b);
    if (predicted === actual) correct++;
    for (const key of keys) {
      const target = key === actual ? 1 : 0;
      brier += (probs[key] - target) ** 2;
    }
    logLoss += -Math.log(Math.max(1e-15, probs[actual]));
    const confidence = probs[predicted];
    const bin = bins[Math.min(9, Math.floor(confidence * 10))];
    bin.count++;
    bin.confidence_sum += confidence;
    bin.accuracy_sum += predicted === actual ? 1 : 0;
  }
  const n = settled.length;
  return {
    total,
    pending: total - n,
    settled: n,
    accuracy: correct / n,
    brier_score: brier / n,
    log_loss: logLoss / n,
    calibration: bins.filter(b => b.count).map(b => ({
      range: (b.bin / 10).toFixed(1) + "-" + ((b.bin + 1) / 10).toFixed(1),
      count: b.count,
      mean_confidence: b.confidence_sum / b.count,
      observed_accuracy: b.accuracy_sum / b.count
    }))
  };
}

async function handle(request, env) {
  const url = new URL(request.url);
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
  if (url.pathname === "/") return json({ name: "FMIS", version: "0.3.0", docs: "Cloudflare Worker API", health: "/api/health" });
  if (url.pathname === "/api/health" && request.method === "GET") {
    const dataset = await env.FMIS_DATA.get("dataset:v1", "json");
    const legacyRows = dataset ? null : await env.FMIS_DATA.get("matches", "json");
    const rows = dataset?.matches ?? legacyRows ?? [];
    return json({
      status: "ok",
      version: "0.3.0",
      storage: "cloudflare_kv",
      matches_loaded: rows.length,
      dataset_updated_at: dataset?.updated_at ?? null
    });
  }
  if (url.pathname === "/api/data/info" && request.method === "GET") {
    const dataset = await env.FMIS_DATA.get("dataset:v1", "json");
    const legacyRows = dataset ? null : await env.FMIS_DATA.get("matches", "json");
    const rows = dataset?.matches ?? legacyRows ?? [];
    return json({
      status: rows.length ? "loaded" : "empty",
      storage: "cloudflare_kv",
      matches_loaded: rows.length,
      updated_at: dataset?.updated_at ?? null,
      columns: dataset?.columns ?? null
    });
  }
  if (url.pathname === "/api/data/csv" && request.method === "POST") {
    if (!env.FMIS_ADMIN_TOKEN) return fail("FMIS_ADMIN_TOKEN secret is not configured", 503);
    if (request.headers.get("X-Admin-Token") !== env.FMIS_ADMIN_TOKEN) return fail("Invalid admin token", 401);
    const form = await request.formData();
    const file = form.get("file");
    if (!file || typeof file.text !== "function") return fail("A CSV file is required");
    if (file.size > 10 * 1024 * 1024) return fail("CSV file exceeds 10 MB limit", 413);
    try {
      const parsed = parseCsv((await file.text()).replace(/^\uFEFF/, ""));
      const dataset = {
        schema_version: 1,
        updated_at: new Date().toISOString(),
        row_count: parsed.matches.length,
        columns: parsed.columns,
        matches: parsed.matches
      };
      const serialized = JSON.stringify(dataset);
      if (new TextEncoder().encode(serialized).byteLength > 25 * 1024 * 1024) {
        return fail("Parsed dataset exceeds the 25 MB Cloudflare KV value limit", 413);
      }
      // Store the complete dataset and its metadata in one KV value so readers
      // never observe a new metadata record paired with an old matches record.
      await env.FMIS_DATA.put("dataset:v1", serialized);
      return json({
        status: "loaded",
        loaded: parsed.matches.length,
        columns: parsed.columns,
        storage: "cloudflare_kv",
        updated_at: dataset.updated_at
      });
    } catch (e) { return fail(e.message, 422); }
  }
  if (url.pathname === "/api/predictions" && request.method === "POST") {
    if (!env.FMIS_ADMIN_TOKEN) return fail("FMIS_ADMIN_TOKEN secret is not configured", 503);
    if (request.headers.get("X-Admin-Token") !== env.FMIS_ADMIN_TOKEN) return fail("Invalid admin token", 401);
    let body;
    try { body = await request.json(); } catch { return fail("Request body must be valid JSON"); }
    const fixture = body?.fixture;
    const prediction = body?.prediction;
    const probs = prediction?.markets?.["1x2"];
    if (!fixture || typeof fixture.home_team !== "string" || !fixture.home_team.trim() ||
        typeof fixture.away_team !== "string" || !fixture.away_team.trim() ||
        fixture.home_team.trim().toLowerCase() === fixture.away_team.trim().toLowerCase() ||
        typeof fixture.as_of !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(fixture.as_of)) {
      return fail("A valid fixture with home_team, away_team and as_of is required");
    }
    if (!probs || !["home", "draw", "away"].every(k => typeof probs[k] === "number" && Number.isFinite(probs[k]) && probs[k] >= 0 && probs[k] <= 1) ||
        Math.abs(probs.home + probs.draw + probs.away - 1) > 0.002) {
      return fail("Prediction must include valid normalized 1X2 probabilities");
    }
    const id = crypto.randomUUID();
    const record = {
      id,
      status: "pending",
      created_at: new Date().toISOString(),
      fixture,
      probabilities: { home: probs.home, draw: probs.draw, away: probs.away },
      prediction,
      data_quality: body.data_quality ?? null,
      actual: null,
      settled_at: null
    };
    await env.FMIS_DATA.put("prediction:" + id, JSON.stringify(record));
    return json({ status: "saved", prediction: record }, 201);
  }
  if (url.pathname === "/api/predictions" && request.method === "GET") {
    const page = await env.FMIS_DATA.list({ prefix: "prediction:", limit: 1000 });
    const values = await Promise.all(page.keys.map(item => env.FMIS_DATA.get(item.name, "json")));
    let records = values.filter(Boolean);
    const status = url.searchParams.get("status");
    if (status === "pending" || status === "settled") records = records.filter(r => r.status === status);
    records.sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
    return json({ predictions: records, count: records.length, list_complete: page.list_complete });
  }
  if (url.pathname === "/api/tracker/metrics" && request.method === "GET") {
    const records = await listPredictions(env.FMIS_DATA);
    return json(trackerMetrics(records));
  }
  const resultMatch = url.pathname.match(/^\/api\/predictions\/([0-9a-f-]+)\/result$/i);
  if (resultMatch && request.method === "POST") {
    if (!env.FMIS_ADMIN_TOKEN) return fail("FMIS_ADMIN_TOKEN secret is not configured", 503);
    if (request.headers.get("X-Admin-Token") !== env.FMIS_ADMIN_TOKEN) return fail("Invalid admin token", 401);
    const id = resultMatch[1];
    const key = "prediction:" + id;
    const record = await env.FMIS_DATA.get(key, "json");
    if (!record) return fail("Prediction not found", 404);
    if (record.status === "settled") return fail("This prediction already has an actual result", 409);
    let body;
    try { body = await request.json(); } catch { return fail("Request body must be valid JSON"); }
    const homeGoals = body?.home_goals, awayGoals = body?.away_goals;
    if (!validScore(homeGoals) || !validScore(awayGoals)) return fail("Actual goals must be non-negative whole numbers up to 30");
    record.actual = { home_goals: homeGoals, away_goals: awayGoals, outcome: outcomeFor(homeGoals, awayGoals) };
    record.status = "settled";
    record.settled_at = new Date().toISOString();
    await env.FMIS_DATA.put(key, JSON.stringify(record));
    return json({ status: "settled", prediction: record });
  }
  if (url.pathname === "/api/analyze" && request.method === "POST") {
    const dataset = await env.FMIS_DATA.get("dataset:v1", "json");
    const legacyRows = dataset ? null : await env.FMIS_DATA.get("matches", "json");
    const matches = dataset?.matches ?? legacyRows ?? [];
    if (!matches.length) return fail("No historical data loaded. Upload a CSV first.", 409);
    let body;
    try { body = await request.json(); } catch { return fail("Request body must be valid JSON"); }
    const { home_team, away_team, as_of, total_line = 2.5, handicap_home = -0.5 } = body || {};
    if (typeof home_team !== "string" || !home_team.trim() || typeof away_team !== "string" || !away_team.trim()) return fail("Home and away team names are required");
    if (typeof as_of !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(as_of) || Number.isNaN(Date.parse(as_of + "T00:00:00Z"))) return fail("as_of must be a valid YYYY-MM-DD date");
    if (typeof total_line !== "number" || total_line < 0.5 || total_line > 8.5 || Math.abs(total_line * 4 - Math.round(total_line * 4)) > 1e-8) return fail("total_line must be between 0.5 and 8.5 in quarter-goal increments");
    if (typeof handicap_home !== "number" || handicap_home < -3 || handicap_home > 3 || Math.abs(handicap_home * 4 - Math.round(handicap_home * 4)) > 1e-8) return fail("handicap_home must be between -3 and 3 in quarter-goal increments");
    const prior = matches.filter(m => m.date < as_of);
    try {
      const [lh, la, dataQuality] = estimateLambdas(prior, home_team, away_team);
      const prediction = predict(lh, la, total_line, handicap_home);
      return json({
        fixture: { home_team, away_team, as_of },
        data_quality: { basis: dataQuality, prior_matches: prior.length, as_of },
        prediction,
        analyst: explain(home_team, away_team, prediction, dataQuality)
      });
    } catch (e) { return fail(e.message, 422); }
  }
  return fail("Not found", 404);
}

export default {
  async fetch(request, env) {
    try { return await handle(request, env); }
    catch (error) { return fail("Internal error: " + (error && error.message ? error.message : "unknown"), 500); }
  }
};
