/// audio.hpp — audio scenario: deep 3-level inheritance hierarchy.
#pragma once

namespace audio {

enum class NodeType   { Source = 0, Sink = 1, Effect = 2 };
enum class SampleRate { Hz44100 = 44100, Hz48000 = 48000, Hz96000 = 96000 };

// ---- Level 1: AudioNode (base) ----

class AudioNode {
public:
    AudioNode() = default;
    explicit AudioNode(const char* name) : name_(name) {}

    const char* getName() const { return name_; }
    void        setName(const char* n) { name_ = n; }

    NodeType getNodeType() const { return type_; }

    bool isEnabled() const { return enabled_; }
    void setEnabled(bool e) { enabled_ = e; }

    virtual const char* nodeClass() const { return "AudioNode"; }

    double gain_ = 1.0;

protected:
    NodeType    type_    = NodeType::Source;
    bool        enabled_ = true;

private:
    const char* name_ = "node";
};

// ---- Level 2a: AudioSource (derives AudioNode) ----

class AudioSource : public AudioNode {
public:
    AudioSource() = default;
    explicit AudioSource(const char* name) : AudioNode(name) {}

    int  getChannels() const { return channels_; }
    void setChannels(int c) { channels_ = c; }

    double getSampleRate() const { return sampleRate_; }
    void   setSampleRate(double sr) { sampleRate_ = sr; }

    const char* nodeClass() const override { return "AudioSource"; }

    static AudioSource create(const char* name) { return AudioSource(name); }

private:
    double sampleRate_ = 44100.0;
    int    channels_   = 2;
};

// ---- Level 2b: AudioEffect (derives AudioNode) ----

class AudioEffect : public AudioNode {
public:
    AudioEffect() = default;
    explicit AudioEffect(const char* name) : AudioNode(name) {}

    double getMix() const { return mix_; }
    void   setMix(double m) { mix_ = (m < 0.0 ? 0.0 : (m > 1.0 ? 1.0 : m)); }

    const char* nodeClass() const override { return "AudioEffect"; }

private:
    double mix_ = 0.5;
};

// ---- Level 3a: Reverb (derives AudioEffect) ----

class Reverb : public AudioEffect {
public:
    Reverb() = default;
    explicit Reverb(double roomSize) : roomSize_(roomSize) {}
    Reverb(double roomSize, double decay) : roomSize_(roomSize), decay_(decay) {}

    double getRoomSize() const { return roomSize_; }
    void   setRoomSize(double r) { roomSize_ = r; }

    double getDecay() const { return decay_; }
    void   setDecay(double d) { decay_ = d; }

    const char* nodeClass() const override { return "Reverb"; }

    static Reverb room()    { return Reverb(0.8, 0.7); }
    static Reverb chamber() { return Reverb(0.5, 0.5); }

public:
    double roomSize_ = 0.5;
    double decay_    = 0.5;
};

// ---- Level 3b: Delay (derives AudioEffect) ----

class Delay : public AudioEffect {
public:
    Delay() = default;
    explicit Delay(double delayTime) : delayTime_(delayTime) {}
    Delay(double delayTime, double feedback) : delayTime_(delayTime), feedback_(feedback) {}

    double getDelayTime() const { return delayTime_; }
    void   setDelayTime(double t) { delayTime_ = t; }

    double getFeedback() const { return feedback_; }
    void   setFeedback(double f) { feedback_ = (f < 0.0 ? 0.0 : (f > 1.0 ? 1.0 : f)); }

    const char* nodeClass() const override { return "Delay"; }

    static Delay echo() { return Delay(0.5, 0.4); }
    static Delay slap() { return Delay(0.1, 0.2); }

public:
    double delayTime_ = 0.25;
    double feedback_  = 0.3;
};

} // namespace audio
