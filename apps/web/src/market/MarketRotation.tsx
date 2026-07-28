import { useEffect, useMemo, useState } from "react";

import { RotationChart } from "./RotationChart";
import {
  Inspector,
  Playback,
  RotationHeader,
  RotationStatus,
} from "./RotationPanels";
import type { RotationSpeed } from "./RotationPanels";
import type { Quadrant, RotationSnapshot } from "./rotationTypes";
import { quadrantLabels } from "./rotationTypes";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8010";

type LoadState =
  | { kind: "loading" }
  | { kind: "ready"; snapshot: RotationSnapshot }
  | { kind: "empty" }
  | { kind: "corrupt" }
  | { kind: "error"; message: string };

let rotationRequest: Promise<LoadState> | undefined;

function loadRotationSnapshot(): Promise<LoadState> {
  rotationRequest ??= fetch(`${apiBaseUrl}/api/market/industry-rotation`)
    .then(async (response): Promise<LoadState> => {
      if (response.status === 404) return { kind: "empty" };
      if (response.status === 503) return { kind: "corrupt" };
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return { kind: "ready", snapshot: (await response.json()) as RotationSnapshot };
    })
    .catch((error: unknown) => ({
      kind: "error",
      message: error instanceof Error ? error.message : "未知错误",
    }));
  return rotationRequest;
}

function initialParams() {
  const params = new URLSearchParams(window.location.search);
  return {
    date: params.get("as_of"),
    selected: params.get("industry") ?? "",
    trail: Number(params.get("trail")) || 20,
    quadrant: (params.get("quadrant") ?? "") as Quadrant | "",
    recentOnly: params.get("events") === "recent",
  };
}

export function MarketRotation() {
  const initial = useMemo(initialParams, []);
  const [load, setLoad] = useState<LoadState>({ kind: "loading" });
  const [dateIndex, setDateIndex] = useState(-1);
  const [selected, setSelected] = useState(initial.selected);
  const [trail, setTrail] = useState(initial.trail);
  const [quadrant, setQuadrant] = useState<Quadrant | "">(initial.quadrant);
  const [recentOnly, setRecentOnly] = useState(initial.recentOnly);
  const [onlySelected, setOnlySelected] = useState(false);
  const [search, setSearch] = useState("");
  const [speed, setSpeed] = useState<RotationSpeed>(1);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    let active = true;
    loadRotationSnapshot().then((result) => {
      if (!active) return;
      setLoad(result);
      if (result.kind === "ready") {
        const snapshot = result.snapshot;
        const requested = initial.date ? snapshot.dates.indexOf(initial.date) : -1;
        setDateIndex(requested >= 0 ? requested : snapshot.dates.length - 1);
        setSelected((value) => value || snapshot.points[0]?.industry_code || "");
      }
    });
    return () => { active = false; };
  }, [initial.date]);

  const snapshot = load.kind === "ready" ? load.snapshot : null;
  const currentDate = snapshot?.dates[dateIndex] ?? "";
  const current = useMemo(
    () => snapshot?.points.filter((point) => point.trade_date === currentDate) ?? [],
    [snapshot, currentDate],
  );
  const recentCodes = useMemo(() => {
    if (!snapshot) return new Set<string>();
    const start = snapshot.dates[Math.max(0, dateIndex - 4)];
    return new Set(
      snapshot.events
        .filter((event) => event.confirmed_date >= start && event.confirmed_date <= currentDate)
        .map((event) => event.industry_code),
    );
  }, [snapshot, dateIndex, currentDate]);
  const dimmed = useMemo(
    () =>
      new Set(
        current
          .filter((point) => {
            const searchMiss = search && !point.industry_name.includes(search.trim());
            const quadrantMiss = quadrant && point.quadrant !== quadrant;
            const eventMiss = recentOnly && !recentCodes.has(point.industry_code);
            const selectionMiss = onlySelected && point.industry_code !== selected;
            return searchMiss || quadrantMiss || eventMiss || selectionMiss;
          })
          .map((point) => point.industry_code),
      ),
    [current, search, quadrant, recentOnly, recentCodes, onlySelected, selected],
  );
  const trails = useMemo(() => {
    if (!snapshot || !selected) return [];
    const start = Math.max(0, dateIndex - trail + 1);
    const dates = new Set(snapshot.dates.slice(start, dateIndex + 1));
    return snapshot.points.filter(
      (point) => point.industry_code === selected && dates.has(point.trade_date),
    );
  }, [snapshot, selected, dateIndex, trail]);

  useEffect(() => {
    if (!playing || !snapshot) return;
    const timer = window.setInterval(() => {
      setDateIndex((index) => {
        if (index >= snapshot.dates.length - 1) {
          setPlaying(false);
          return index;
        }
        return index + 1;
      });
    }, 900 / speed);
    return () => window.clearInterval(timer);
  }, [playing, speed, snapshot]);

  useEffect(() => {
    if (!snapshot || dateIndex < 0) return;
    const params = new URLSearchParams({
      tab: "industries", view: "rotation", as_of: currentDate,
      trail: String(trail), industry: selected,
    });
    if (quadrant) params.set("quadrant", quadrant);
    if (recentOnly) params.set("events", "recent");
    window.history.replaceState(null, "", `/market?${params}`);
  }, [snapshot, currentDate, dateIndex, trail, selected, quadrant, recentOnly]);

  if (load.kind !== "ready") return <RotationStatus state={load} />;
  return <ReadyRotation snapshot={load.snapshot} current={current} trails={trails}
    selected={selected} setSelected={setSelected} dimmed={dimmed} dateIndex={dateIndex}
    setDateIndex={setDateIndex} playing={playing} setPlaying={setPlaying} speed={speed}
    setSpeed={setSpeed} trail={trail} setTrail={setTrail} search={search}
    setSearch={setSearch} quadrant={quadrant} setQuadrant={setQuadrant}
    recentOnly={recentOnly} setRecentOnly={setRecentOnly} onlySelected={onlySelected}
    setOnlySelected={setOnlySelected} recentCodes={recentCodes} currentDate={currentDate} />;
}

type ReadyProps = {
  snapshot: RotationSnapshot; current: RotationSnapshot["points"]; trails: RotationSnapshot["points"];
  selected: string; setSelected: (value: string) => void; dimmed: Set<string>;
  dateIndex: number; setDateIndex: (value: number) => void;
  playing: boolean; setPlaying: (value: boolean) => void;
  speed: RotationSpeed; setSpeed: (value: RotationSpeed) => void;
  trail: number; setTrail: (value: number) => void; search: string; setSearch: (value: string) => void;
  quadrant: Quadrant | ""; setQuadrant: (value: Quadrant | "") => void;
  recentOnly: boolean; setRecentOnly: (value: boolean) => void;
  onlySelected: boolean; setOnlySelected: (value: boolean) => void;
  recentCodes: Set<string>; currentDate: string;
};

function ReadyRotation(props: ReadyProps) {
  const { snapshot, current, trails, selected, setSelected, dimmed, dateIndex,
    setDateIndex, playing, setPlaying, speed, setSpeed, trail, setTrail, search,
    setSearch, quadrant, setQuadrant, recentOnly, setRecentOnly, onlySelected,
    setOnlySelected, currentDate } = props;
  const selectedPoint = current.find((point) => point.industry_code === selected) ?? current[0];
  const counts = Object.fromEntries(
    Object.keys(quadrantLabels).map((key) => [
      key, current.filter((point) => point.quadrant === key).length,
    ]),
  );
  const event = [...snapshot.events].reverse().find(
    (item) => item.industry_code === selected && item.confirmed_date <= currentDate,
  );

  return (
    <div className="rotation-app">
      <RotationHeader snapshot={snapshot} />
      <main className="rotation-main">
        <div className="market-tabs" aria-label="市场视图">
          <span>大盘</span><strong>行业</strong><span>ETF 轮动</span>
          <i /><span>行业热力</span><strong>相对轮动</strong>
        </div>
        <section className="rotation-tools" aria-label="轮动筛选">
          <input aria-label="搜索行业" placeholder="搜索行业" value={search}
            onChange={(event) => setSearch(event.target.value)} />
          <select aria-label="象限筛选" value={quadrant}
            onChange={(event) => setQuadrant(event.target.value as Quadrant | "")}>
            <option value="">全部象限</option>
            {Object.entries(quadrantLabels).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
          <label><input type="checkbox" checked={onlySelected}
            onChange={(event) => setOnlySelected(event.target.checked)} />仅选中</label>
          <label><input type="checkbox" checked={recentOnly}
            onChange={(event) => setRecentOnly(event.target.checked)} />仅近期跃迁</label>
          <span className="quadrant-counts">
            领先 {counts.leading} · 降温 {counts.weakening} · 落后 {counts.lagging} · 改善 {counts.improving}
          </span>
        </section>
        <div className="rotation-workspace">
          <div>
            <RotationChart current={current} trails={trails} selectedCode={selected}
              dimmedCodes={dimmed} onSelect={setSelected} />
            <Playback dates={snapshot.dates} dateIndex={dateIndex} setDateIndex={setDateIndex}
              playing={playing} setPlaying={setPlaying} speed={speed} setSpeed={setSpeed}
              trail={trail} setTrail={setTrail} />
          </div>
          <Inspector point={selectedPoint} event={event} snapshot={snapshot} />
        </div>
      </main>
    </div>
  );
}
