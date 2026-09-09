<!-- 소제목 포함 여부 설정 컨트롤러 -->
<div class="subtitle-option-panel">
  <div class="panel-header">
    <strong>소제목 포함 옵션 설정</strong>
    <span class="desc">글 작성 방식별로 소제목 생성/포함 여부를 선택하세요.</span>
  </div>

  <div class="option-grid">
    <!-- 1. AI 자동글 -->
    <div class="option-item">
      <span class="item-title">AI 자동글</span>
      <div class="btn-group">
        <label class="toggle-btn">
          <input type="radio" name="sub_ai_auto" value="use" checked>
          <span>소제목 포함</span>
        </label>
        <label class="toggle-btn">
          <input type="radio" name="sub_ai_auto" value="none">
          <span>소제목 제외</span>
        </label>
      </div>
    </div>

    <!-- 2. 수동글 -->
    <div class="option-item">
      <span class="item-title">수동글</span>
      <div class="btn-group">
        <label class="toggle-btn">
          <input type="radio" name="sub_manual" value="use">
          <span>소제목 포함</span>
        </label>
        <label class="toggle-btn">
          <input type="radio" name="sub_manual" value="none" checked>
          <span>소제목 제외</span>
        </label>
      </div>
    </div>

    <!-- 3. AI 자동프롬프트글 -->
    <div class="option-item">
      <span class="item-title">AI 자동프롬프트글</span>
      <div class="btn-group">
        <label class="toggle-btn">
          <input type="radio" name="sub_ai_prompt" value="use" checked>
          <span>소제목 포함</span>
        </label>
        <label class="toggle-btn">
          <input type="radio" name="sub_ai_prompt" value="none">
          <span>소제목 제외</span>
        </label>
      </div>
    </div>
  </div>
</div>
