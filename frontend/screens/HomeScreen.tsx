// screens/HomeScreen.tsx — AI Legislative Analyzer · Citizen's Dashboard

import { Ionicons } from "@expo/vector-icons";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import React, { useEffect, useRef } from "react";
import {
  Animated,
  Dimensions,
  Platform,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Accent, useTheme } from "../context/ThemeContext";

const { width: SW } = Dimensions.get("window");

// ─── Animated entrance hook ───────────────────────────────────────────────────

const useFadeSlide = (delay = 0) => {
  const opacity = useRef(new Animated.Value(0)).current;
  const translateY = useRef(new Animated.Value(22)).current;
  useEffect(() => {
    Animated.parallel([
      Animated.timing(opacity, {
        toValue: 1,
        duration: 520,
        delay,
        useNativeDriver: true,
      }),
      Animated.spring(translateY, {
        toValue: 0,
        delay,
        useNativeDriver: true,
        speed: 14,
        bounciness: 5,
      }),
    ]).start();
  }, []);
  return { opacity, transform: [{ translateY }] };
};

// ─── Pulsing live dot ─────────────────────────────────────────────────────────

const PulseDot = () => {
  const scale = useRef(new Animated.Value(1)).current;
  const opacity = useRef(new Animated.Value(0.7)).current;
  useEffect(() => {
    Animated.loop(
      Animated.parallel([
        Animated.sequence([
          Animated.timing(scale, {
            toValue: 1.9,
            duration: 900,
            useNativeDriver: true,
          }),
          Animated.timing(scale, {
            toValue: 1,
            duration: 900,
            useNativeDriver: true,
          }),
        ]),
        Animated.sequence([
          Animated.timing(opacity, {
            toValue: 0,
            duration: 900,
            useNativeDriver: true,
          }),
          Animated.timing(opacity, {
            toValue: 0.7,
            duration: 900,
            useNativeDriver: true,
          }),
        ]),
      ]),
    ).start();
  }, []);
  return (
    <View style={hd.wrap}>
      <Animated.View style={[hd.ring, { transform: [{ scale }], opacity }]} />
      <View style={hd.dot} />
    </View>
  );
};

// ─── Stat card ────────────────────────────────────────────────────────────────

interface StatCardProps {
  value: string;
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  delay: number;
}
const StatCard = ({ value, label, icon, color, delay }: StatCardProps) => {
  const { theme: T } = useTheme();
  const anim = useFadeSlide(delay);
  return (
    <Animated.View
      style={[
        scards.card,
        { backgroundColor: T.bgCard, borderColor: T.border },
        anim,
      ]}
    >
      <View style={[scards.icon, { backgroundColor: color + "22" }]}>
        <Ionicons name={icon} size={20} color={color} />
      </View>
      <Text style={[scards.value, { color: T.textPrimary }]}>{value}</Text>
      <Text style={[scards.label, { color: T.textMuted }]}>{label}</Text>
    </Animated.View>
  );
};

// ─── Feature row ──────────────────────────────────────────────────────────────

interface FeatureRowProps {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  desc: string;
  g1: string;
  g2: string;
  delay: number;
}
const FeatureRow = ({ icon, label, desc, g1, g2, delay }: FeatureRowProps) => {
  const { theme: T } = useTheme();
  const anim = useFadeSlide(delay);
  return (
    <Animated.View
      style={[
        fr.wrap,
        { backgroundColor: T.bgCard, borderColor: T.border },
        anim,
      ]}
    >
      <LinearGradient colors={[g1, g2]} style={fr.iconBox}>
        <Ionicons name={icon} size={20} color="#fff" />
      </LinearGradient>
      <View style={{ flex: 1 }}>
        <Text style={[fr.label, { color: T.textPrimary }]}>{label}</Text>
        <Text style={[fr.desc, { color: T.textMuted }]}>{desc}</Text>
      </View>
      <Ionicons name="chevron-forward" size={15} color={T.textMuted} />
    </Animated.View>
  );
};

// ─── Constraint badge ─────────────────────────────────────────────────────────

const ConstraintBadge = ({ text, delay }: { text: string; delay: number }) => {
  const { theme: T } = useTheme();
  const anim = useFadeSlide(delay);
  return (
    <Animated.View
      style={[
        cbg.wrap,
        {
          backgroundColor: T.isDark
            ? "rgba(124,58,237,0.13)"
            : "rgba(109,40,217,0.06)",
          borderColor: T.borderStrong,
        },
        anim,
      ]}
    >
      <Ionicons name="chevron-forward" size={13} color={Accent.violet400} />
      <Text style={[cbg.text, { color: T.textSecondary }]}>{text}</Text>
    </Animated.View>
  );
};

// ─── Section divider ──────────────────────────────────────────────────────────

const Divider = ({ label }: { label: string }) => {
  const { theme: T } = useTheme();
  return (
    <View style={dv.row}>
      <View style={[dv.line, { backgroundColor: T.border }]} />
      <Text style={[dv.text, { color: T.textMuted }]}>
        {label.toUpperCase()}
      </Text>
      <View style={[dv.line, { backgroundColor: T.border }]} />
    </View>
  );
};

// ─── Screen ───────────────────────────────────────────────────────────────────

export default function HomeScreen() {
  const router = useRouter();
  const { theme: T } = useTheme();
  const insets = useSafeAreaInsets();
  const heroAnim = useFadeSlide(60);

  return (
    <View style={[hs.root, { backgroundColor: T.bg }]}>
      <StatusBar barStyle={T.statusBar} />

      {T.isDark && (
        <>
          <View style={hs.glow1} />
          <View style={hs.glow2} />
          <View style={hs.glow3} />
        </>
      )}

      <ScrollView
        contentContainerStyle={[
          hs.scroll,
          { paddingTop: insets.top + 12, paddingBottom: insets.bottom + 120 },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {/* ── Top bar ── */}
        <View style={hs.topBar}>
          <View>
            <Text style={[hs.projectTag, { color: T.textMuted }]}>
              PROJECT 3
            </Text>
            <Text style={[hs.appName, { color: T.textPrimary }]}>Digital Sansad</Text>
          </View>
          <View style={hs.topRight}>
            <PulseDot />
            <Text style={[hs.liveLabel, { color: Accent.green }]}>Live</Text>
            <View
              style={[
                hs.shieldBadge,
                { backgroundColor: T.bgCard2, borderColor: T.border },
              ]}
            >
              <Ionicons
                name="shield-checkmark"
                size={14}
                color={Accent.violet400}
              />
            </View>
          </View>
        </View>

        {/* ── Hero card ── */}
        <Animated.View style={[hs.heroCard, heroAnim]}>
          <LinearGradient
            colors={
              T.isDark
                ? ["#1e0d40", "#110720", "#080612"]
                : ["#ede9fe", "#ddd6fe", "#f5f3ff"]
            }
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={hs.heroGrad}
          >
            <View
              style={[
                hs.heroShimmer,
                {
                  backgroundColor: T.isDark
                    ? "rgba(196,181,253,0.14)"
                    : "rgba(109,40,217,0.1)",
                },
              ]}
            />

            {/* Eyebrow badge */}
            <LinearGradient
              colors={Accent.gradAI}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 0 }}
              style={hs.eyebrow}
            >
              <Ionicons name="sparkles" size={11} color="#fff" />
              <Text style={hs.eyebrowText}>AI Legislative Analyzer</Text>
            </LinearGradient>

            <Text style={[hs.heroTitle, { color: T.textPrimary }]}>
              {"Citizen's\nDashboard"}
            </Text>
            <Text style={[hs.heroSub, { color: T.textSecondary }]}>
              Real-time, simplified summaries of Indian laws and parliamentary
              bills — built for every citizen, not just lawyers.
            </Text>

            <View style={hs.ctaRow}>
              <TouchableOpacity activeOpacity={0.85} style={hs.ctaPrimaryWrap}>
                <LinearGradient
                  colors={Accent.gradAI}
                  start={{ x: 0, y: 0 }}
                  end={{ x: 1, y: 0 }}
                  style={hs.ctaPrimary}
                >
                  <Ionicons name="document-text" size={16} color="#fff" />
                  <Text style={hs.ctaPrimaryText}>Analyse a Bill</Text>
                </LinearGradient>
              </TouchableOpacity>
              <TouchableOpacity
                activeOpacity={0.8}
                style={[
                  hs.ctaSecondary,
                  {
                    backgroundColor: T.isDark
                      ? "rgba(255,255,255,0.07)"
                      : "rgba(109,40,217,0.08)",
                    borderColor: T.borderStrong,
                  },
                ]}
              >
                <Ionicons
                  name="library-outline"
                  size={16}
                  color={Accent.violet400}
                />
                <Text
                  style={[hs.ctaSecondaryText, { color: Accent.violet400 }]}
                >
                  Browse Laws
                </Text>
              </TouchableOpacity>
            </View>
          </LinearGradient>
        </Animated.View>

        {/* ── Stats ── */}
        <View style={hs.statsRow}>
          <StatCard
            value="100k+"
            label="Token Limit"
            icon="layers-outline"
            color={Accent.violet500}
            delay={160}
          />
          <StatCard
            value="94%"
            label="Compression"
            icon="git-merge-outline"
            color={Accent.fuchsia}
            delay={220}
          />
          <StatCard
            value="↓82%"
            label="Carbon Cost"
            icon="leaf-outline"
            color={Accent.green}
            delay={280}
          />
        </View>

        {/* ── Context ── */}
        <Divider label="The Problem" />
        <Animated.View
          style={[
            hs.contextCard,
            { backgroundColor: T.bgCard, borderColor: T.border },
            useFadeSlide(300),
          ]}
        >
          <View style={[hs.quoteBar, { backgroundColor: Accent.violet500 }]} />
          <Text style={[hs.contextText, { color: T.textSecondary }]}>
            Indian law and parliamentary bills are{" "}
            <Text style={{ color: T.textPrimary, fontWeight: "700" }}>
              dense, verbose, and inaccessible
            </Text>{" "}
            to the average citizen. Summarizing them with raw LLMs is{" "}
            <Text style={{ color: Accent.fuchsia, fontWeight: "700" }}>
              energy-intensive and environmentally costly.
            </Text>
          </Text>
        </Animated.View>

        {/* ── Constraints ── */}
        <Divider label="Key Constraints" />
        <ConstraintBadge
          text="Must handle documents exceeding 100,000 tokens"
          delay={340}
        />
        <ConstraintBadge
          text="Judged on Information Density — maximum value per token consumed"
          delay={380}
        />
        <ConstraintBadge
          text="Token Compression required to shrink docs into high-density prompts"
          delay={420}
        />

        {/* ── Required technique ── */}
        <Divider label="Required Technique" />
        <Animated.View style={[hs.techniqueCard, useFadeSlide(460)]}>
          <LinearGradient
            colors={T.isDark ? ["#2d1060", "#180830"] : ["#ddd6fe", "#ede9fe"]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={hs.techniqueInner}
          >
            <View style={hs.techniqueHeader}>
              <LinearGradient
                colors={["#d946ef", "#a855f7"]}
                style={hs.techniqueIconBox}
              >
                <Ionicons name="flash" size={18} color="#fff" />
              </LinearGradient>
              <View>
                <Text style={[hs.techniqueEyebrow, { color: T.textMuted }]}>
                  METHOD
                </Text>
                <Text style={[hs.techniqueTitle, { color: T.textPrimary }]}>
                  Token Compression
                </Text>
              </View>
            </View>
            <Text style={[hs.techniqueBody, { color: T.textSecondary }]}>
              Shrinks massive legal documents into high-density prompts without
              sacrificing meaning — directly cutting inference cost and carbon
              footprint per summary.
            </Text>
            <View
              style={[
                hs.techniquePill,
                {
                  backgroundColor: T.isDark
                    ? "rgba(217,70,239,0.18)"
                    : "rgba(217,70,239,0.1)",
                },
              ]}
            >
              <Ionicons name="trending-down" size={13} color={Accent.fuchsia} />
              <Text style={[hs.techniquePillText, { color: Accent.fuchsia }]}>
                Fewer tokens · Lower carbon · Higher signal
              </Text>
            </View>
          </LinearGradient>
        </Animated.View>

        {/* ── Features ── */}
        <Divider label="Features" />
        <FeatureRow
          icon="scan-outline"
          label="Real-time Bill Tracker"
          desc="Monitor new parliamentary bills as they enter Lok Sabha & Rajya Sabha"
          g1="#7c3aed"
          g2="#a855f7"
          delay={500}
        />
        <FeatureRow
          icon="document-text-outline"
          label="Plain-English Summaries"
          desc="Dense legal language converted to clear, citizen-friendly explanations"
          g1="#6d28d9"
          g2="#7c3aed"
          delay={540}
        />
        <FeatureRow
          icon="git-merge-outline"
          label="Compression Engine"
          desc="100k+ token documents compressed without loss of critical information"
          g1="#a855f7"
          g2="#d946ef"
          delay={580}
        />
        <FeatureRow
          icon="leaf-outline"
          label="Carbon Cost Tracker"
          desc="Live metric: energy saved per summary vs raw LLM inference"
          g1="#059669"
          g2="#10b981"
          delay={620}
        />
        <FeatureRow
          icon="notifications-outline"
          label="Policy Alerts"
          desc="Push notifications when bills affecting your interests are tabled"
          g1="#d946ef"
          g2="#f59e0b"
          delay={660}
        />

        {/* ── Judging criterion ── */}
        <Animated.View style={useFadeSlide(700)}>
          <LinearGradient
            colors={
              T.isDark
                ? ["rgba(124,58,237,0.22)", "rgba(26,19,48,0.85)"]
                : ["rgba(109,40,217,0.1)", "rgba(237,233,254,0.95)"]
            }
            style={[hs.judgeCard, { borderColor: T.borderStrong }]}
          >
            <View style={hs.judgeTop}>
              <Ionicons
                name="trophy-outline"
                size={22}
                color={Accent.violet400}
              />
              <Text style={[hs.judgeHeading, { color: T.textPrimary }]}>
                Judging Criterion
              </Text>
            </View>
            <Text style={[hs.judgeMetric, { color: Accent.violet300 }]}>
              Information Density
            </Text>
            <Text style={[hs.judgeDesc, { color: T.textSecondary }]}>
              Winning solutions maximise the value delivered per token consumed.
              Every byte counts.
            </Text>
          </LinearGradient>
        </Animated.View>
      </ScrollView>
    </View>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const hs = StyleSheet.create({
  root: { flex: 1 },
  glow1: {
    position: "absolute",
    top: -60,
    left: -60,
    width: 280,
    height: 280,
    borderRadius: 140,
    backgroundColor: "rgba(109,40,217,0.15)",
  },
  glow2: {
    position: "absolute",
    top: 220,
    right: -80,
    width: 220,
    height: 220,
    borderRadius: 110,
    backgroundColor: "rgba(217,70,239,0.08)",
  },
  glow3: {
    position: "absolute",
    bottom: 320,
    left: -40,
    width: 180,
    height: 180,
    borderRadius: 90,
    backgroundColor: "rgba(124,58,237,0.09)",
  },

  scroll: { paddingHorizontal: 18 },

  topBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 20,
  },
  projectTag: {
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 2.5,
    marginBottom: 2,
  },
  appName: { fontSize: 30, fontWeight: "900", letterSpacing: -1.2 },
  topRight: { flexDirection: "row", alignItems: "center", gap: 8 },
  liveLabel: { fontSize: 12, fontWeight: "700", letterSpacing: 0.5 },
  shieldBadge: {
    width: 34,
    height: 34,
    borderRadius: 11,
    borderWidth: 1,
    justifyContent: "center",
    alignItems: "center",
  },

  heroCard: {
    borderRadius: 24,
    overflow: "hidden",
    marginBottom: 14,
    ...Platform.select({
      ios: {
        shadowColor: "#4c1d95",
        shadowOffset: { width: 0, height: 14 },
        shadowOpacity: 0.35,
        shadowRadius: 28,
      },
      android: { elevation: 14 },
    }),
  },
  heroGrad: { padding: 22, paddingBottom: 24 },
  heroShimmer: {
    position: "absolute",
    top: 0,
    left: 28,
    right: 28,
    height: 1,
    borderRadius: 99,
  },

  eyebrow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    alignSelf: "flex-start",
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 99,
    marginBottom: 16,
  },
  eyebrowText: {
    fontSize: 11,
    fontWeight: "700",
    color: "#fff",
    letterSpacing: 0.4,
  },

  heroTitle: {
    fontSize: 36,
    fontWeight: "900",
    letterSpacing: -1.2,
    lineHeight: 40,
    marginBottom: 10,
  },
  heroSub: {
    fontSize: 14,
    lineHeight: 22,
    letterSpacing: 0.1,
    marginBottom: 22,
  },

  ctaRow: { flexDirection: "row", gap: 10 },
  ctaPrimaryWrap: { flex: 1, borderRadius: 14, overflow: "hidden" },
  ctaPrimary: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
    paddingVertical: 13,
  },
  ctaPrimaryText: { fontSize: 14, fontWeight: "700", color: "#fff" },
  ctaSecondary: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
    paddingVertical: 12,
    borderRadius: 14,
    borderWidth: 1,
  },
  ctaSecondaryText: { fontSize: 14, fontWeight: "700" },

  statsRow: { flexDirection: "row", gap: 10, marginBottom: 4 },

  contextCard: {
    flexDirection: "row",
    borderRadius: 18,
    borderWidth: 1,
    overflow: "hidden",
    marginBottom: 8,
  },
  quoteBar: { width: 4, borderRadius: 2, margin: 16, marginRight: 0 },
  contextText: {
    flex: 1,
    fontSize: 14,
    lineHeight: 22,
    padding: 16,
    paddingLeft: 14,
  },

  techniqueCard: {
    borderRadius: 20,
    overflow: "hidden",
    marginBottom: 8,
    ...Platform.select({
      ios: {
        shadowColor: "#d946ef",
        shadowOffset: { width: 0, height: 8 },
        shadowOpacity: 0.22,
        shadowRadius: 20,
      },
      android: { elevation: 10 },
    }),
  },
  techniqueInner: { padding: 20 },
  techniqueHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    marginBottom: 12,
  },
  techniqueIconBox: {
    width: 44,
    height: 44,
    borderRadius: 14,
    justifyContent: "center",
    alignItems: "center",
  },
  techniqueEyebrow: {
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 1.5,
    marginBottom: 2,
  },
  techniqueTitle: { fontSize: 20, fontWeight: "800", letterSpacing: -0.5 },
  techniqueBody: { fontSize: 13, lineHeight: 20, marginBottom: 14 },
  techniquePill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    alignSelf: "flex-start",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 99,
  },
  techniquePillText: { fontSize: 12, fontWeight: "600" },

  judgeCard: { borderRadius: 20, borderWidth: 1, padding: 20, marginBottom: 8 },
  judgeTop: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    marginBottom: 6,
  },
  judgeHeading: { fontSize: 16, fontWeight: "700" },
  judgeMetric: {
    fontSize: 28,
    fontWeight: "900",
    letterSpacing: -1,
    marginBottom: 8,
  },
  judgeDesc: { fontSize: 13, lineHeight: 20 },
});

const scards = StyleSheet.create({
  card: {
    flex: 1,
    borderRadius: 16,
    borderWidth: 1,
    padding: 13,
    alignItems: "center",
    gap: 5,
    ...Platform.select({
      ios: {
        shadowColor: "#4c1d95",
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.12,
        shadowRadius: 10,
      },
      android: { elevation: 4 },
    }),
  },
  icon: {
    width: 38,
    height: 38,
    borderRadius: 12,
    justifyContent: "center",
    alignItems: "center",
  },
  value: { fontSize: 17, fontWeight: "800", letterSpacing: -0.5 },
  label: {
    fontSize: 10,
    fontWeight: "600",
    letterSpacing: 0.4,
    textAlign: "center",
  },
});

const fr = StyleSheet.create({
  wrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    borderRadius: 18,
    borderWidth: 1,
    padding: 14,
    marginBottom: 10,
    ...Platform.select({
      ios: {
        shadowColor: "#4c1d95",
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.08,
        shadowRadius: 12,
      },
      android: { elevation: 3 },
    }),
  },
  iconBox: {
    width: 44,
    height: 44,
    borderRadius: 14,
    justifyContent: "center",
    alignItems: "center",
  },
  label: {
    fontSize: 14,
    fontWeight: "700",
    letterSpacing: 0.1,
    marginBottom: 3,
  },
  desc: { fontSize: 12, lineHeight: 17 },
});

const cbg = StyleSheet.create({
  wrap: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10,
    borderRadius: 14,
    borderWidth: 1,
    padding: 14,
    marginBottom: 8,
  },
  text: { flex: 1, fontSize: 13, lineHeight: 19, fontWeight: "500" },
});

const dv = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    marginTop: 20,
    marginBottom: 14,
  },
  line: { flex: 1, height: 1 },
  text: { fontSize: 10, fontWeight: "800", letterSpacing: 1.8 },
});

const hd = StyleSheet.create({
  wrap: {
    width: 14,
    height: 14,
    justifyContent: "center",
    alignItems: "center",
  },
  ring: {
    position: "absolute",
    width: 14,
    height: 14,
    borderRadius: 7,
    backgroundColor: Accent.green,
  },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: Accent.green },
});
