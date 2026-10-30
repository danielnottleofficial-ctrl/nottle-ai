from nottle_ai.voice import Transcript


def test_completed_response_releases_partial_text_and_renders_once():
    transcript = Transcript()
    transcript.ai_delta("response-1", "Partial response")
    transcript.ai_done("response-1", "The complete response")

    assert not transcript.ai_deltas
    assert transcript.render() == "AI: The complete response"
    assert transcript.render() == "AI: The complete response"


def test_streaming_transcript_is_bounded_before_completion():
    transcript = Transcript()
    for _ in range(2000):
        transcript.ai_delta("response-1", "x" * 100)

    assert len(transcript.ai_deltas["response-1"]) == 5000
    transcript.ai_done("response-1")
    assert not transcript.ai_deltas
    assert transcript.render() == "AI: " + "x" * 5000


def test_many_completed_responses_leave_no_streaming_buffers():
    transcript = Transcript()
    for number in range(1000):
        item = f"response-{number}"
        transcript.ai_delta(item, "partial")
        transcript.ai_done(item, f"Answer {number}")

    assert not transcript.ai_deltas
    rendered = transcript.render().splitlines()
    assert len(rendered) == 1000
    assert rendered[0] == "AI: Answer 0"
    assert rendered[-1] == "AI: Answer 999"
