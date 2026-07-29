import { useId, useState } from "react";

import { motionLabels } from "./rotationIdentity";
import type { RotationScreenRow } from "./rotationScreening";
import type { RotationPoint } from "./rotationTypes";
import { industryColor } from "./rotationIdentity";

export function IndustryCombobox({
  industries,
  rows,
  selectedCode,
  search,
  onSearch,
  onSelect,
}: {
  industries: RotationPoint[];
  rows: RotationScreenRow[];
  selectedCode: string;
  search: string;
  onSearch: (value: string) => void;
  onSelect: (code: string) => void;
}) {
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const selected = industries.find((item) => item.industry_code === selectedCode);
  const options = rows;

  const choose = (code: string) => {
    onSelect(code);
    onSearch("");
    setOpen(false);
    setActiveIndex(0);
  };

  return (
    <div
      className="industry-combobox"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setOpen(false);
        }
      }}
    >
      <input
        aria-activedescendant={
          open && options[activeIndex]
            ? `${listId}-${options[activeIndex].code}`
            : undefined
        }
        aria-autocomplete="list"
        aria-controls={listId}
        aria-expanded={open}
        aria-label="选择或搜索行业"
        onChange={(event) => {
          onSearch(event.target.value);
          setOpen(true);
          setActiveIndex(0);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            const wasOpen = open;
            setOpen(true);
            setActiveIndex((index) =>
              wasOpen ? Math.min(index + 1, options.length - 1) : 0,
            );
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActiveIndex((index) => Math.max(0, index - 1));
          } else if (event.key === "Enter" && open && options[activeIndex]) {
            event.preventDefault();
            choose(options[activeIndex].code);
          } else if (event.key === "Escape") {
            setOpen(false);
            onSelect("");
            onSearch("");
          }
        }}
        placeholder={selected ? `已选：${selected.industry_name}` : "选择或搜索行业"}
        role="combobox"
        type="text"
        value={search}
      />
      <button
        aria-label="展开行业列表"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        {rows.length} / {industries.length} 个一级行业
        <span aria-hidden="true">⌄</span>
      </button>
      {selected ? (
        <button aria-label="清除行业选择" onClick={() => choose("")} type="button">
          清除
        </button>
      ) : null}
      {open ? (
        <IndustryOptions
          activeIndex={activeIndex}
          listId={listId}
          onActive={setActiveIndex}
          onChoose={choose}
          options={options}
          selectedCode={selectedCode}
        />
      ) : null}
    </div>
  );
}

function IndustryOptions({
  options,
  selectedCode,
  activeIndex,
  listId,
  onActive,
  onChoose,
}: {
  options: RotationScreenRow[];
  selectedCode: string;
  activeIndex: number;
  listId: string;
  onActive: (index: number) => void;
  onChoose: (code: string) => void;
}) {
  return <ul aria-label="申万一级行业" className="industry-options"
    id={listId} role="listbox">
    {options.length ? options.map((item, index) => (
      <li
        aria-selected={item.code === selectedCode}
        className={index === activeIndex ? "is-active" : ""}
        id={`${listId}-${item.code}`}
        key={item.code}
        onMouseDown={(event) => event.preventDefault()}
        onMouseEnter={() => onActive(index)}
        onClick={() => onChoose(item.code)}
        role="option"
      >
        <span><i aria-hidden="true" className="industry-color"
          style={{ background: industryColor(item.code) }} />
          {item.name}</span>
        <code>{item.code}</code>
        {item.point ? <small>
          X {item.point.relative_trend.toFixed(2)} ·
          Y {item.point.relative_momentum.toFixed(2)} ·
          速度 {item.speed?.toFixed(2) ?? "—"} · {motionLabels[item.motion]}
        </small> : null}
      </li>
    )) : <li className="industry-empty">没有匹配的一级行业</li>}
  </ul>;
}
