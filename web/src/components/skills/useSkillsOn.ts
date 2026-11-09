import { useEffect, useState } from "react";
import { listSkills } from "../../api/skills";
import { useLiveState } from "../../hooks/useLiveStore";

// How many skills are on for this bot, for the Skills fold's summary ("3 on"); null until known.
// Read from the server's list, again on skills_changed. A failed read leaves the summary out (the fold says why).
export function useSkillsOn(botId: string): number | null {
  const version = useLiveState().skillVersion?.skills;
  const [count, setCount] = useState<number | null>(null);
  useEffect(() => {
    let live = true;
    listSkills(botId)
      .then((skills) => { if (live) setCount(skills.filter((skill) => skill.on !== false).length); })
      .catch((err: unknown) => { console.warn("Could not count this bot's skills.", err); });
    return () => { live = false; };
  }, [botId, version]);
  return count;
}
