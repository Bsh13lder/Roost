import { useShowFinished } from "../hooks/useShowFinished";
import { Switch } from "../ui/Switch";

// "Show finished" wherever tasks show (lead task 14). `hidden` is how many finished tasks the view is leaving out,
// said beside the switch while it is off, so an empty-looking list is never a mystery.
export function ShowFinishedSwitch({ hidden = 0 }: { hidden?: number }) {
  const [show, setShow] = useShowFinished();
  return (
    <span className="show-finished">
      <Switch checked={show} onChange={setShow}>Show finished</Switch>
      {!show && hidden > 0 ? <span className="show-finished__count">{hidden} finished hidden</span> : null}
    </span>
  );
}
