import { ChartScene } from "../components/ChartScene";
import { MiniCard } from "../components/MiniCard";
import { cardTexts, copy, formatRatio } from "../copy";
import { theme } from "../theme";
import { videoData } from "../data";
import { CARD_APPEAR } from "../timeline";

// CR = 1 is the point where capture equals issuance; the axis starts at zero so the gap is not exaggerated.
const PARITY = 1;

export const Coverage: React.FC<{ pulse?: number }> = ({ pulse = 0 }) => (
  <ChartScene
    text={copy.coverage}
    highlight={["outgrow"]}
    series={[videoData.cr.map((p) => ({ date: p.date, value: p.cr30 })), videoData.cr.map((p) => ({ date: p.date, value: p.cr90 }))]}
    colors={[theme.accentDeep, theme.accentLight]}
    names={[`coverage ratio, ${videoData.windows.mid}d`, `coverage ratio, ${videoData.windows.long}d`]}
    source="coverage.json"
    formatValue={formatRatio}
    pulse={pulse}
    yMax={PARITY}
    refLine={{ value: PARITY, label: "capture = issuance" }}
    refGap="gap to parity"
  >
    <MiniCard {...cardTexts(videoData.cards).distribution} appearAt={CARD_APPEAR.distribution} pulse={pulse} style={{ position: "absolute", left: 60, top: "9%" }} />
  </ChartScene>
);
