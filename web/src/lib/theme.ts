import type { Color } from "../types";

export const DISEASE_FILL: Record<Color, string> = {
  blue: "#2f7de1",
  yellow: "#f2c315",
  black: "#3a3a42",
  red: "#e0403a",
};

export const ROLE_STYLE: Record<string, { fill: string; text: string; initials: string }> = {
  contingency_planner: { fill: "#3cc7d6", text: "#043", initials: "CP" },
  dispatcher: { fill: "#f58fb5", text: "#400", initials: "D" },
  medic: { fill: "#ff9a2e", text: "#310", initials: "M" },
  operations_expert: { fill: "#7ed957", text: "#142", initials: "OE" },
  quarantine_specialist: { fill: "#1f7a4a", text: "#fff", initials: "QS" },
  researcher: { fill: "#9a6b3f", text: "#fff", initials: "R" },
  scientist: { fill: "#f4f4f4", text: "#223", initials: "S" },
};
