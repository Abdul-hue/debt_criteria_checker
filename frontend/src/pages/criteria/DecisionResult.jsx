import { useState } from "react";

const SOLUTION_CONFIG = {
  IVA: {
    label: "IVA Eligible",
    bg: "bg-emerald-50",
    border: "border-emerald-200",
    badge: "bg-emerald-600 text-white",
    icon: "✓",
    iconBg: "bg-emerald-100 text-emerald-700",
    title: "Case meets IVA criteria",
  },
  UNCLEAR: {
    label: "Review Required",
    bg: "bg-amber-50",
    border: "border-amber-200",
    badge: "bg-amber-500 text-white",
    icon: "!",
    iconBg: "bg-amber-100 text-amber-700",
    title: "Manual review required before proceeding",
  },
  DMP: {
    label: "DMP Recommended",
    bg: "bg-blue-50",
    border: "border-blue-200",
    badge: "bg-blue-600 text-white",
    icon: "→",
    iconBg: "bg-blue-100 text-blue-700",
    title: "Debt Management Plan is the appropriate solution",
  },
  FORCED_DMP_VAT: {
    label: "DMP Recommended",
    bg: "bg-blue-50",
    border: "border-blue-200",
    badge: "bg-blue-600 text-white",
    icon: "→",
    iconBg: "bg-blue-100 text-blue-700",
    title: "Previous-year HMRC VAT debt — automatic IVA fail, DMP required",
  },
  FREE_SECTOR: {
    label: "Free Sector",
    bg: "bg-slate-50",
    border: "border-slate-200",
    badge: "bg-slate-600 text-white",
    icon: "○",
    iconBg: "bg-slate-100 text-slate-700",
    title: "Refer to free sector debt advice",
  },
};

/**
 * Safe numeric formatter for pence to GBP strings.
 */
function formatPence(pence) {
  if (pence == null || isNaN(Number(pence))) return "—";
  const pounds = Number(pence) / 100;
  return "£" + pounds.toLocaleString("en-GB", { minimumFractionDigits: 2 });
}

/**
 * Safe numeric formatter for pence-per-pound dividend.
 */
function formatDividend(pence) {
  if (pence == null || isNaN(Number(pence))) return "—";
  return Math.round(Number(pence) / 100) + "p/£";
}

function Pill({ children, color }) {
  const colors = {
    red:   "bg-red-100 text-red-700 border border-red-200",
    amber: "bg-amber-100 text-amber-700 border border-amber-200",
    green: "bg-emerald-100 text-emerald-700 border border-emerald-200",
    slate: "bg-slate-100 text-slate-600 border border-slate-200",
    blue:  "bg-blue-100 text-blue-700 border border-blue-200",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colors[color] || colors.slate}`}>
      {children}
    </span>
  );
}

function SectionHeader({ icon, title, count, countColor }) {
  const countColors = {
    red:   "bg-red-600 text-white",
    amber: "bg-amber-500 text-white",
    green: "bg-emerald-600 text-white",
    slate: "bg-slate-400 text-white",
  };
  return (
    <div className="flex items-center justify-between mb-3">
      <div className="flex items-center gap-2">
        <span className="text-base">{icon}</span>
        <h3 className="text-sm font-semibold text-slate-800 tracking-wide uppercase">
          {title}
        </h3>
      </div>
      {count != null && (
        <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${countColors[countColor] || countColors.slate}`}>
          {count}
        </span>
      )}
    </div>
  );
}

function BlockCard({ item, type }) {
  const [open, setOpen] = useState(false);
  if (!item) return null;

  const isHard = type === "hard";
  const borderColor = isHard ? "border-red-200 bg-red-50" : "border-amber-200 bg-amber-50";
  const dotColor    = isHard ? "bg-red-500" : "bg-amber-500";

  return (
    <div
      className={`rounded-lg border ${borderColor} p-3 cursor-pointer select-none`}
      onClick={() => setOpen(!open)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2 min-w-0">
          <span className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${dotColor}`} />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-slate-800">
              {String(item.rule_name || item.rule_key || "Unknown Rule")}
            </p>
            {item.creditor_specific && (
              <p className="text-xs text-slate-500 mt-0.5">
                Creditor:{" "}
                <span className="font-medium text-slate-700">{String(item.creditor_specific)}</span>
              </p>
            )}
          </div>
        </div>
        <span className="text-slate-400 text-xs flex-shrink-0 mt-0.5">
          {open ? "▲" : "▼"}
        </span>
      </div>

      {open && (
        <div className="mt-3 pt-3 border-t border-slate-200 space-y-2">
          {item.message && (
            <p className="text-xs text-slate-700 leading-relaxed">{String(item.message)}</p>
          )}
          {item.action_required && (
            <div className="flex items-start gap-1.5">
              <span className="text-amber-600 text-xs font-bold flex-shrink-0">Action:</span>
              <p className="text-xs text-slate-700">{String(item.action_required)}</p>
            </div>
          )}
          <p className="text-xs text-slate-400 font-mono italic">{String(item.rule_key || "")}</p>
        </div>
      )}
    </div>
  );
}

function PassedCard({ item }) {
  if (!item) return null;
  return (
    <div className="flex items-start gap-2 py-2 border-b border-slate-100 last:border-0">
      <span className="mt-0.5 text-emerald-500 text-sm flex-shrink-0">✓</span>
      <div>
        <p className="text-sm text-slate-700 font-medium">
          {String(item.rule_name || item.rule_key || "Passed Check")}
        </p>
        {item.message && (
          <p className="text-xs text-slate-400 mt-0.5">{String(item.message)}</p>
        )}
      </div>
    </div>
  );
}

function FactRow({ label, value, highlight }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-slate-100 last:border-0">
      <span className="text-xs text-slate-500">{String(label)}</span>
      <span className={`text-sm font-semibold ${highlight ? "text-emerald-700" : "text-slate-800"}`}>
        {String(value)}
      </span>
    </div>
  );
}

export default function DecisionResult({ result, applicationId }) {
  // Defensive extraction — ensure we always have an object to work with
  let data = {};
  try {
    data = result?.data || result || {};
  } catch (e) {
    console.error("Error extracting decision data:", e);
  }

  // Basic guard against completely missing results
  if (!data || Object.keys(data).length === 0 || (!data.recommended_solution && !data.decision_summary)) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-10 text-center">
        <p className="text-slate-400 text-sm italic">No assessment data available for this reference.</p>
        <p className="text-slate-300 text-xs mt-2 font-mono">Reference: {applicationId || "None"}</p>
      </div>
    );
  }

  // Defensive mappings with fallback types
  const solution    = String(data.recommended_solution || "UNCLEAR");
  const config      = SOLUTION_CONFIG[solution] || SOLUTION_CONFIG.UNCLEAR;
  const hardBlocks  = Array.isArray(data.hard_blocks)    ? data.hard_blocks    : [];
  const flags       = Array.isArray(data.flags)           ? data.flags           : [];
  const passed      = Array.isArray(data.passed_checks)   ? data.passed_checks   : [];
  const infoItems   = Array.isArray(data.info)            ? data.info            : [];

  const totalDebt   = data.total_unsecured_debt ?? data.total_debt_pence ?? null;
  const di          = data.disposable_income ?? null;
  const dividend    = data.estimated_dividend_pence ?? null;
  const watchPresent = !!data.watch_creditor_present;
  
  // Safe majority creditor extraction
  const majorityObj = data.majority_creditor;
  const majorityName = (majorityObj && typeof majorityObj === 'object') ? (majorityObj.name || null) : null;
  
  const passesAll   = !!data.passes_all_hard_blocks;
  const summary     = data.decision_summary ? String(data.decision_summary) : null;
  const triggeredBy = data.triggered_by ? String(data.triggered_by) : null;
  const triggeredAt = data.triggered_at ? String(data.triggered_at) : null;

  return (
    <div className="space-y-5">

      {/* Decision Banner */}
      <div className={`rounded-xl border-2 ${config.border} ${config.bg} p-5`}>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-start gap-3">
            <div className={`w-10 h-10 rounded-full flex items-center justify-center text-lg font-bold flex-shrink-0 ${config.iconBg}`}>
              {config.icon}
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-xl font-bold text-slate-900">{config.title}</h2>
                <span className={`text-xs font-bold px-2.5 py-1 rounded-full tracking-wide ${config.badge}`}>
                  {solution}
                </span>
              </div>
              {summary && (
                <p className="text-sm text-slate-600 mt-1.5 leading-relaxed max-w-2xl">
                  {summary}
                </p>
              )}
            </div>
          </div>
          <div className="flex flex-col items-end gap-1.5">
            <Pill color={passesAll ? "green" : "red"}>
              {passesAll
                ? "Passes all hard checks"
                : `${hardBlocks.length} hard block${hardBlocks.length !== 1 ? "s" : ""} found`}
            </Pill>
            {watchPresent && <Pill color="amber">WATCH creditor present</Pill>}
            {majorityName && <Pill color="blue">Majority creditor: {majorityName}</Pill>}
          </div>
        </div>
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

        {/* Left — blocks, flags, passed */}
        <div className="lg:col-span-2 space-y-5">

          {/* Hard Blocks */}
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <SectionHeader
              icon="🚫"
              title="Hard Blocks"
              count={hardBlocks.length}
              countColor={hardBlocks.length > 0 ? "red" : "slate"}
            />
            {hardBlocks.length === 0 ? (
              <p className="text-sm text-slate-400 italic">
                No hard blocks — case clears all blocking criteria.
              </p>
            ) : (
              <div className="space-y-2">
                {hardBlocks.map((item, i) => (
                  <BlockCard key={i} item={item} type="hard" />
                ))}
              </div>
            )}
          </div>

          {/* Flags */}
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <SectionHeader
              icon="⚠️"
              title="Flags — Assessor Review Required"
              count={flags.length}
              countColor={flags.length > 0 ? "amber" : "slate"}
            />
            {flags.length === 0 ? (
              <p className="text-sm text-slate-400 italic">No flags raised.</p>
            ) : (
              <div className="space-y-2">
                {flags.map((item, i) => (
                  <BlockCard key={i} item={item} type="flag" />
                ))}
              </div>
            )}
          </div>

          {/* Passed Checks */}
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <SectionHeader
              icon="✅"
              title="Passed Checks"
              count={passed.length}
              countColor="green"
            />
            {passed.length === 0 ? (
              <p className="text-sm text-slate-400 italic">No checks recorded as passed.</p>
            ) : (
              <div>
                {passed.map((item, i) => (
                  <PassedCard key={i} item={item} />
                ))}
              </div>
            )}
          </div>

          {/* Info items */}
          {infoItems.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 p-5">
              <SectionHeader
                icon="ℹ️"
                title="Additional Information"
                count={infoItems.length}
                countColor="slate"
              />
              <div className="space-y-2">
                {infoItems.map((item, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-2 py-2 border-b border-slate-100 last:border-0"
                  >
                    <span className="text-blue-400 text-sm flex-shrink-0">•</span>
                    <div>
                      <p className="text-sm text-slate-700 font-medium">
                        {String(item.rule_name || item.rule_key || "Info")}
                      </p>
                      {item.message && (
                        <p className="text-xs text-slate-400 mt-0.5">{String(item.message)}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right — key facts */}
        <div className="space-y-4">

          {/* Financial summary */}
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
              Financial Summary
            </h3>
            {totalDebt != null && (
              <FactRow label="Total unsecured debt" value={formatPence(totalDebt)} />
            )}
            {di != null && (
              <FactRow label="Monthly disposable income" value={formatPence(di)} />
            )}
            {dividend != null && (
              <FactRow
                label="Estimated dividend"
                value={formatDividend(dividend)}
                highlight={Number(dividend) >= 2000}
              />
            )}
            {totalDebt == null && di == null && dividend == null && (
              <p className="text-xs text-slate-400 italic">Financial data not available.</p>
            )}
          </div>

          {/* Assessment facts */}
          <div className="bg-white rounded-xl border border-slate-200 p-5">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
              Assessment Facts
            </h3>
            <FactRow label="Potential solution" value={solution} />
            <FactRow label="Passes hard blocks" value={passesAll ? "Yes" : "No"} />
            <FactRow label="Hard block count" value={hardBlocks.length} />
            <FactRow label="Flag count" value={flags.length} />
            <FactRow label="Passed checks" value={passed.length} />
            <FactRow label="WATCH creditor" value={watchPresent ? "Yes" : "No"} />
            <FactRow label="Majority creditor" value={majorityName ?? "None"} />
            {applicationId && (
              <FactRow label="Application ref" value={String(applicationId)} />
            )}
            {triggeredBy && (
              <FactRow label="Assessed by" value={triggeredBy} />
            )}
            {triggeredAt && (
              <FactRow
                label="Assessment time"
                value={new Date(triggeredAt).toLocaleString("en-GB", {
                  day: "2-digit",
                  month: "short",
                  year: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              />
            )}
          </div>

          {/* WATCH warning */}
          {watchPresent && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
              <p className="text-xs font-bold text-amber-700 uppercase tracking-wide mb-1">
                WATCH Creditor Detected
              </p>
              <p className="text-xs text-amber-600 leading-relaxed">
                This case includes a WATCH-managed creditor. Speak with Tom or
                Debra before booking the case in if anything falls outside criteria.
              </p>
            </div>
          )}

          {/* Majority creditor warning */}
          {majorityName && (
            <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
              <p className="text-xs font-bold text-blue-700 uppercase tracking-wide mb-1">
                Majority Creditor
              </p>
              <p className="text-xs text-blue-600 leading-relaxed">
                <strong>{majorityName}</strong> holds 75%+ of total debt. Their
                specific criteria must be satisfied for the IVA to proceed.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
