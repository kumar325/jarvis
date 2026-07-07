import type { DocumentEntry } from "../../lib/types";
import { PanelFrame } from "./PanelFrame";

interface Props {
  documents: DocumentEntry[];
}

export function Documents({ documents }: Props) {
  return (
    <PanelFrame title="DOCUMENTS">
      <ul className="flex flex-col gap-1.5">
        {documents.map((doc) => (
          <li
            key={doc.id}
            className="flex items-center justify-between text-xs font-mono text-slate-300"
          >
            <span className="truncate">{doc.name}</span>
            <span className="text-slate-500 text-[0.6rem] ml-2 shrink-0">{doc.accessedAt}</span>
          </li>
        ))}
      </ul>
    </PanelFrame>
  );
}
