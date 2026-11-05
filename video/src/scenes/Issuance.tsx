import { ChartScene } from "../components/ChartScene";
import { copy, formatCompact } from "../copy";
import { theme } from "../theme";
import { videoData } from "../data";

export const Issuance: React.FC<{ pulse?: number }> = ({ pulse = 0 }) => (
  <ChartScene
    text={copy.issuance}
    highlight={["issues"]}
    series={[videoData.issuance]}
    colors={[theme.accent]}
    names={["NEAR issued/day"]}
    source="coverage.json"
    formatValue={formatCompact}
    pulse={pulse}
  />
);
