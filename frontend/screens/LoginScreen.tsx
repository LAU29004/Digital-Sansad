// screens/LoginScreen.tsx — Premium Violet AI Login with Google Auth

import { Ionicons } from "@expo/vector-icons";
import { LinearGradient } from "expo-linear-gradient";
import React, { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Animated,
  Platform,
  StatusBar,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Accent, useTheme } from "../context/ThemeContext";

// ─── Props ────────────────────────────────────────────────────────────────────

interface LoginScreenProps {
  onLoginSuccess: () => void;
}

// ─── Google SVG logo (inline, no image deps) ─────────────────────────────────

const GoogleLogo = ({ size = 20 }: { size?: number }) => (
  <View style={{ width: size, height: size }}>
    {/* G shape using colored views — avoids SVG/image deps */}
    <View
      style={[gl.wrap, { width: size, height: size, borderRadius: size / 2 }]}
    >
      <View
        style={[
          gl.blue,
          {
            width: size * 0.55,
            height: size * 0.1,
            top: size * 0.45,
            left: size * 0.45,
          },
        ]}
      />
      <View
        style={[
          gl.blue,
          {
            width: size * 0.1,
            height: size * 0.28,
            top: size * 0.45,
            left: size * 0.45,
          },
        ]}
      />
      <View
        style={[
          gl.blue,
          {
            width: size * 0.45,
            height: size * 0.1,
            top: size * 0.45,
            left: size * 0.45,
            opacity: 0,
          },
        ]}
      />
    </View>
    {/* Render proper G using Text as fallback */}
    <Text style={[gl.gText, { fontSize: size * 0.72, lineHeight: size }]}>
      G
    </Text>
  </View>
);

const gl = StyleSheet.create({
  wrap: { position: "relative", overflow: "hidden" },
  blue: { position: "absolute", backgroundColor: "#4285F4" },
  gText: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    textAlign: "center",
    fontWeight: "700",
    color: "#4285F4",
    fontFamily: Platform.select({ ios: "Georgia", android: "serif" }),
  },
});

// ─── Floating orb ─────────────────────────────────────────────────────────────

const FloatingOrb = ({
  size,
  color,
  delay,
  duration,
  startX,
  startY,
}: {
  size: number;
  color: string;
  delay: number;
  duration: number;
  startX: number;
  startY: number;
}) => {
  const translateY = useRef(new Animated.Value(0)).current;
  const opacity = useRef(new Animated.Value(0.4)).current;

  useEffect(() => {
    Animated.loop(
      Animated.parallel([
        Animated.sequence([
          Animated.timing(translateY, {
            toValue: -18,
            duration,
            delay,
            useNativeDriver: true,
          }),
          Animated.timing(translateY, {
            toValue: 0,
            duration,
            useNativeDriver: true,
          }),
        ]),
        Animated.sequence([
          Animated.timing(opacity, {
            toValue: 0.7,
            duration: duration * 0.5,
            delay,
            useNativeDriver: true,
          }),
          Animated.timing(opacity, {
            toValue: 0.3,
            duration: duration * 0.5,
            useNativeDriver: true,
          }),
        ]),
      ]),
    ).start();
  }, []);

  return (
    <Animated.View
      style={{
        position: "absolute",
        left: startX,
        top: startY,
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: color,
        opacity,
        transform: [{ translateY }],
      }}
    />
  );
};

// ─── Feature chip ─────────────────────────────────────────────────────────────

const FeatureChip = ({
  icon,
  label,
  delay,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  delay: number;
}) => {
  const { theme: T } = useTheme();
  const opacity = useRef(new Animated.Value(0)).current;
  const translateX = useRef(new Animated.Value(-12)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(opacity, {
        toValue: 1,
        duration: 400,
        delay,
        useNativeDriver: true,
      }),
      Animated.spring(translateX, {
        toValue: 0,
        delay,
        useNativeDriver: true,
        speed: 16,
        bounciness: 5,
      }),
    ]).start();
  }, []);

  return (
    <Animated.View
      style={[
        fc.chip,
        {
          backgroundColor: T.isDark
            ? "rgba(139,92,246,0.15)"
            : "rgba(109,40,217,0.08)",
          borderColor: T.borderStrong,
          opacity,
          transform: [{ translateX }],
        },
      ]}
    >
      <LinearGradient colors={Accent.gradAI} style={fc.iconWrap}>
        <Ionicons name={icon} size={12} color="#fff" />
      </LinearGradient>
      <Text style={[fc.label, { color: T.textSecondary }]}>{label}</Text>
    </Animated.View>
  );
};

const fc = StyleSheet.create({
  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 99,
    borderWidth: 1,
  },
  iconWrap: {
    width: 20,
    height: 20,
    borderRadius: 6,
    justifyContent: "center",
    alignItems: "center",
  },
  label: { fontSize: 12, fontWeight: "600", letterSpacing: 0.2 },
});

// ─── Screen ───────────────────────────────────────────────────────────────────

export default function LoginScreen({ onLoginSuccess }: LoginScreenProps) {
  const { theme: T, isDark } = useTheme();
  const insets = useSafeAreaInsets();
  const [loading, setLoading] = useState(false);
  const [loadingEmail, setLoadingEmail] = useState(false);

  // Entrance animations
  const logoScale = useRef(new Animated.Value(0.7)).current;
  const logoOpacity = useRef(new Animated.Value(0)).current;
  const cardSlide = useRef(new Animated.Value(40)).current;
  const cardOpacity = useRef(new Animated.Value(0)).current;
  const titleSlide = useRef(new Animated.Value(20)).current;
  const titleOpacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.sequence([
      // Logo springs in
      Animated.parallel([
        Animated.spring(logoScale, {
          toValue: 1,
          useNativeDriver: true,
          speed: 12,
          bounciness: 8,
        }),
        Animated.timing(logoOpacity, {
          toValue: 1,
          duration: 400,
          useNativeDriver: true,
        }),
      ]),
      // Title fades up
      Animated.parallel([
        Animated.spring(titleSlide, {
          toValue: 0,
          useNativeDriver: true,
          speed: 16,
          bounciness: 5,
        }),
        Animated.timing(titleOpacity, {
          toValue: 1,
          duration: 380,
          useNativeDriver: true,
        }),
      ]),
      // Card slides up
      Animated.parallel([
        Animated.spring(cardSlide, {
          toValue: 0,
          useNativeDriver: true,
          speed: 14,
          bounciness: 6,
        }),
        Animated.timing(cardOpacity, {
          toValue: 1,
          duration: 420,
          useNativeDriver: true,
        }),
      ]),
    ]).start();
  }, []);

  const handleGoogleLogin = async () => {
    setLoading(true);
    // Simulate Google OAuth — replace with real expo-auth-session / @react-native-google-signin/google-signin
    await new Promise((r) => setTimeout(r, 1800));
    setLoading(false);
    onLoginSuccess();
  };

  const handleEmailLogin = async () => {
    setLoadingEmail(true);
    await new Promise((r) => setTimeout(r, 1200));
    setLoadingEmail(false);
    onLoginSuccess();
  };

  return (
    <View style={[ls.root, { backgroundColor: T.bg }]}>
      <StatusBar barStyle={T.statusBar} />

      {/* ── Ambient orbs ── */}
      <FloatingOrb
        size={280}
        color={isDark ? "rgba(109,40,217,0.18)" : "rgba(109,40,217,0.09)"}
        delay={0}
        duration={3200}
        startX={-80}
        startY={-60}
      />
      <FloatingOrb
        size={200}
        color={isDark ? "rgba(217,70,239,0.12)" : "rgba(217,70,239,0.07)"}
        delay={600}
        duration={2800}
        startX={120}
        startY={100}
      />
      <FloatingOrb
        size={160}
        color={isDark ? "rgba(139,92,246,0.14)" : "rgba(139,92,246,0.07)"}
        delay={1200}
        duration={3600}
        startX={-40}
        startY={380}
      />
      <FloatingOrb
        size={120}
        color={isDark ? "rgba(217,70,239,0.10)" : "rgba(217,70,239,0.06)"}
        delay={400}
        duration={2600}
        startX={260}
        startY={500}
      />

      {/* ── Grid overlay (dark only) ── */}
      {isDark && <View style={ls.gridOverlay} />}

      <View
        style={[
          ls.container,
          { paddingTop: insets.top + 20, paddingBottom: insets.bottom + 20 },
        ]}
      >
        {/* ── Logo mark ── */}
        <Animated.View
          style={[
            ls.logoWrap,
            { opacity: logoOpacity, transform: [{ scale: logoScale }] },
          ]}
        >
          <LinearGradient
            colors={Accent.gradAI}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={ls.logoGrad}
          >
            <View style={ls.logoShimmer} />
            <Ionicons name="sparkles" size={32} color="#fff" />
          </LinearGradient>
          {/* Ring pulse */}
          <View
            style={[
              ls.logoRing,
              {
                borderColor: isDark
                  ? "rgba(139,92,246,0.3)"
                  : "rgba(109,40,217,0.2)",
              },
            ]}
          />
          <View
            style={[
              ls.logoRing2,
              {
                borderColor: isDark
                  ? "rgba(139,92,246,0.15)"
                  : "rgba(109,40,217,0.1)",
              },
            ]}
          />
        </Animated.View>

        {/* ── Headline ── */}
        <Animated.View
          style={[
            ls.titleWrap,
            { opacity: titleOpacity, transform: [{ translateY: titleSlide }] },
          ]}
        >
          <Text style={[ls.appName, { color: T.textPrimary }]}>Digital Sansad</Text>
          <Text style={[ls.tagline, { color: T.textSecondary }]}>
            Indian Laws & Policies,{"\n"}Explained for Every Citizen
          </Text>

          {/* Feature chips */}
          <View style={ls.chipsRow}>
            <FeatureChip
              icon="document-text-outline"
              label="Bills & Acts"
              delay={700}
            />
            <FeatureChip
              icon="flash-outline"
              label="AI Summaries"
              delay={820}
            />
            <FeatureChip icon="leaf-outline" label="Low Carbon" delay={940} />
          </View>
        </Animated.View>

        {/* ── Auth card ── */}
        <Animated.View
          style={[
            ls.cardWrap,
            { opacity: cardOpacity, transform: [{ translateY: cardSlide }] },
          ]}
        >
          <View
            style={[
              ls.card,
              { backgroundColor: T.bgCard, borderColor: T.border },
            ]}
          >
            {/* Card shimmer top */}
            <View
              style={[
                ls.cardShimmer,
                {
                  backgroundColor: isDark
                    ? "rgba(196,181,253,0.1)"
                    : "rgba(109,40,217,0.07)",
                },
              ]}
            />

            <Text style={[ls.cardTitle, { color: T.textPrimary }]}>
              Sign in to continue
            </Text>
            <Text style={[ls.cardSub, { color: T.textMuted }]}>
              Access real-time policy insights and AI analysis
            </Text>

            {/* ── Google button ── */}
            <TouchableOpacity
              onPress={handleGoogleLogin}
              activeOpacity={0.85}
              disabled={loading || loadingEmail}
              style={[
                ls.googleBtn,
                {
                  backgroundColor: isDark ? "#ffffff" : "#ffffff",
                  borderColor: isDark
                    ? "rgba(255,255,255,0.12)"
                    : "rgba(0,0,0,0.08)",
                  opacity: loading || loadingEmail ? 0.7 : 1,
                },
              ]}
            >
              {loading ? (
                <ActivityIndicator size="small" color="#4285F4" />
              ) : (
                <>
                  <Text style={ls.googleBtnText}>Continue To Use</Text>
                </>
              )}
            </TouchableOpacity>

            {/* ── Terms ── */}
            <Text style={[ls.terms, { color: T.textMuted }]}>
              By continuing, you agree to our{" "}
              <Text style={[ls.termsLink, { color: Accent.violet400 }]}>
                Terms of Service
              </Text>{" "}
              and{" "}
              <Text style={[ls.termsLink, { color: Accent.violet400 }]}>
                Privacy Policy
              </Text>
            </Text>
          </View>

          {/* ── Trust badges ── */}
          <View style={ls.badgesRow}>
            {[
              {
                icon: "shield-checkmark-outline" as const,
                label: "End-to-end encrypted",
              },
              { icon: "leaf-outline" as const, label: "Carbon neutral AI" },
              { icon: "lock-closed-outline" as const, label: "No data sold" },
            ].map((b) => (
              <View key={b.label} style={ls.badge}>
                <Ionicons name={b.icon} size={13} color={T.textMuted} />
                <Text style={[ls.badgeText, { color: T.textMuted }]}>
                  {b.label}
                </Text>
              </View>
            ))}
          </View>
        </Animated.View>

        {/* ── Version ── */}
        <Text style={[ls.version, { color: T.textMuted }]}>
          Digital Sansad v1.0 · AI Legislative Analyzer
        </Text>
      </View>
    </View>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const ls = StyleSheet.create({
  root: { flex: 1 },
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 24,
  },

  // Subtle dot grid overlay for dark mode depth
  gridOverlay: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    opacity: 0.025,
    backgroundColor: "transparent",
    // Can't do actual dot grid without SVG, but this creates subtle texture
    borderWidth: 0,
  },

  // Logo
  logoWrap: { alignItems: "center", marginTop: 16 },
  logoGrad: {
    width: 80,
    height: 80,
    borderRadius: 26,
    justifyContent: "center",
    alignItems: "center",
    overflow: "hidden",
    ...Platform.select({
      ios: {
        shadowColor: "#7c3aed",
        shadowOffset: { width: 0, height: 12 },
        shadowOpacity: 0.6,
        shadowRadius: 24,
      },
      android: { elevation: 16 },
    }),
  },
  logoShimmer: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    height: 1,
    backgroundColor: "rgba(255,255,255,0.3)",
    borderRadius: 99,
  },
  logoRing: {
    position: "absolute",
    width: 100,
    height: 100,
    borderRadius: 34,
    borderWidth: 1.5,
  },
  logoRing2: {
    position: "absolute",
    width: 122,
    height: 122,
    borderRadius: 40,
    borderWidth: 1,
  },

  // Title
  titleWrap: { alignItems: "center", gap: 10 },
  appName: {
    fontSize: 42,
    fontWeight: "900",
    letterSpacing: -2,
    lineHeight: 44,
  },
  tagline: {
    fontSize: 15,
    lineHeight: 22,
    textAlign: "center",
    letterSpacing: 0.1,
    fontWeight: "400",
  },
  chipsRow: {
    flexDirection: "row",
    gap: 8,
    flexWrap: "wrap",
    justifyContent: "center",
    marginTop: 4,
  },

  // Card
  cardWrap: { width: "100%", gap: 16 },
  card: {
    borderRadius: 24,
    borderWidth: 1,
    padding: 22,
    overflow: "hidden",
    ...Platform.select({
      ios: {
        shadowColor: "#4c1d95",
        shadowOffset: { width: 0, height: 12 },
        shadowOpacity: 0.2,
        shadowRadius: 28,
      },
      android: { elevation: 8 },
    }),
  },
  cardShimmer: {
    position: "absolute",
    top: 0,
    left: 24,
    right: 24,
    height: 1,
    borderRadius: 99,
  },
  cardTitle: {
    fontSize: 20,
    fontWeight: "800",
    letterSpacing: -0.4,
    marginBottom: 4,
  },
  cardSub: {
    fontSize: 13,
    lineHeight: 19,
    letterSpacing: 0.1,
    marginBottom: 20,
  },

  // Google button
  googleBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    paddingVertical: 14,
    borderRadius: 16,
    borderWidth: 1,
    marginBottom: 14,
    ...Platform.select({
      ios: {
        shadowColor: "#000",
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.08,
        shadowRadius: 8,
      },
      android: { elevation: 3 },
    }),
  },
  googleIconWrap: {
    width: 24,
    height: 24,
    borderRadius: 6,
    backgroundColor: "#fff",
    justifyContent: "center",
    alignItems: "center",
    borderWidth: 1,
    borderColor: "rgba(0,0,0,0.06)",
  },
  googleG: {
    fontSize: 16,
    fontWeight: "700",
    color: "#4285F4",
    fontFamily: Platform.select({ ios: "Georgia", android: "serif" }),
    lineHeight: 20,
  },
  googleBtnText: {
    fontSize: 15,
    fontWeight: "700",
    color: "#1f1f1f",
    letterSpacing: 0.1,
  },

  // Divider
  dividerRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    marginBottom: 14,
  },
  dividerLine: { flex: 1, height: 1 },
  dividerText: { fontSize: 12, fontWeight: "600", letterSpacing: 0.5 },

  // Email button
  emailBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    paddingVertical: 14,
    borderRadius: 16,
    borderWidth: 1,
    marginBottom: 18,
  },
  emailBtnText: { fontSize: 15, fontWeight: "700", letterSpacing: 0.1 },

  // Terms
  terms: {
    fontSize: 11,
    textAlign: "center",
    lineHeight: 17,
    letterSpacing: 0.1,
  },
  termsLink: { fontWeight: "700" },

  // Trust badges
  badgesRow: { flexDirection: "row", justifyContent: "center", gap: 16 },
  badge: { flexDirection: "row", alignItems: "center", gap: 5 },
  badgeText: { fontSize: 10, fontWeight: "600", letterSpacing: 0.2 },

  // Version
  version: { fontSize: 11, letterSpacing: 0.3 },
});
