import { marketBusinessText } from "../../business-language/marketBusinessText";
import type { EtfRotationCandidate } from "../types";

export function etfCandidateStateLabel(state: EtfRotationCandidate["state"]) {
  return marketBusinessText(state);
}

export function etfRejectionReasonLabel(value: string) {
  return marketBusinessText(value);
}
