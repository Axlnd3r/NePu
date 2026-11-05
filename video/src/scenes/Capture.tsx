import { ChartScene } from "../components/ChartScene";
import { copy, formatCompact } from "../copy";
import { theme } from "../theme";
import { videoData } from "../data";

export const Capture: React.FC<{ pulse?: number }> = ({ pulse = 0 }) => (
  <ChartScene
    text={copy.capture}
    highlight={["buy", "back"]}
    series={[videoData.issuance, videoData.buyback, videoData.burn]}
    colors={[theme.neutral, theme.accent, theme.series3]}
    names={["issuance", "buyback", "burn"]}
    source="coverage.json"
    formatValue={formatCompact}
    pulse={pulse}
    gap={{ upper: 0, lower: 1, label: "the gap" }}
  />
);
