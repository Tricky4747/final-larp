const COLORS: Record<string, string> = {
  founder: "#e8b84a", Control: "#c08cf0", Validation: "#6cc3e8", Planner: "#7ad3a0",
  LandingPage: "#f08c6c", LeadGen: "#e8d86c", Marketing: "#f06ca8",
};
export const agentColor = (n: string) => COLORS[n] ?? "#9fb0c8";
export const STAGES = ["Validation", "Planner", "LandingPage", "LeadGen", "Marketing", "Control"];
