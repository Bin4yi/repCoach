/** Small drawings that show where to put the phone. Pure SVG, no images to load. */
export default function CameraTips({ view, exercise }: { view: "side" | "front"; exercise: string }) {
  return (
    <div className="card !p-3">
      <h3 className="text-sm font-semibold">How to film</h3>
      <div className="mt-2 flex items-center gap-4">
        <svg viewBox="0 0 220 120" className="h-28 w-48 shrink-0" role="img" aria-label={`Phone ${view} of the person, full body in view`}>
          <rect x="1" y="1" width="218" height="118" rx="10" fill="none" stroke="currentColor" strokeOpacity=".25" />
          {view === "side" ? (
            <g stroke="currentColor" strokeWidth="3" strokeLinecap="round" fill="none">
              <circle cx="110" cy="22" r="8" />
              <path d="M110 30 L106 62 L120 88 L112 108 M106 62 L92 86 L98 108" />
              <path d="M110 40 L126 52" />
            </g>
          ) : (
            <g stroke="currentColor" strokeWidth="3" strokeLinecap="round" fill="none">
              <circle cx="110" cy="22" r="8" />
              <path d="M110 30 L110 66 M110 40 L88 56 M110 40 L132 56 M110 66 L96 108 M110 66 L124 108" />
            </g>
          )}
          <g transform="translate(14 70)" fill="currentColor" opacity=".7">
            <rect width="16" height="28" rx="3" />
            <text x="22" y="18" fontSize="9">phone</text>
          </g>
        </svg>
        <ul className="space-y-1 text-sm">
          <li>📱 Put the phone on a stable surface, about hip height.</li>
          <li>📐 {view === "side" ? "Film from the SIDE" : "Film from the FRONT"} (side is best for {exercise === "squat" ? "depth" : "form"}).</li>
          <li>🧍 Your whole body must be in view, head to feet.</li>
          <li>💡 Good light. Wear fitted clothes. Only you in the shot.</li>
          <li>⏱ Up to 60 seconds, one set.</li>
        </ul>
      </div>
    </div>
  );
}
