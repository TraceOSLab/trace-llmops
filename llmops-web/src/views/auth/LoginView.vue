<script setup lang="ts">
import LoginForm from './components/LoginForm.vue'
</script>
<template>
  <div class="login-page">
    <section class="login-story">
      <router-link to="/home" class="brand"
        ><img src="/favicon.svg" alt="Trace" /><span>Trace <small>LLMOPS</small></span></router-link
      >
      <div class="story-main">
        <p class="eyebrow">IDEAS INTO INTELLIGENCE</p>
        <h1>让想法<br />拥有行动力。</h1>
        <p>连接模型与知识，编排每一个步骤。<br />在一个清晰的工作空间，让 AI 真正为你工作。</p>
        <div class="story-flow">
          <span>知识</span><i>→</i><strong>Trace</strong><i>→</i><span>行动</span>
        </div>
      </div>
      <footer>Built by Youyou <span>Trace LLMOPS</span></footer>
    </section>
    <section class="login-form">
      <div>
        <p class="eyebrow">WELCOME BACK</p>
        <login-form />
        <p class="login-footnote">你的应用、工作流与知识，在这里继续。</p>
      </div>
    </section>
  </div>
</template>
<style scoped>
.login-page {
  min-height: 100dvh;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
}
.login-story {
  padding: 48px 60px;
  background: #eaf1ed;
  display: flex;
  flex-direction: column;
}
.story-main {
  margin: auto 0;
  padding: 60px 0;
}
.story-main h1 {
  font-size: 60px;
  letter-spacing: -3px;
  line-height: 1.3;
  color: #20493b;
  margin: 22px 0;
}
.story-main > p:not(.eyebrow) {
  font-size: 15px;
  line-height: 2;
  color: #718a7e;
}
.story-flow {
  display: flex;
  gap: 20px;
  align-items: center;
  margin-top: 55px;
}
.story-flow span,
.story-flow strong {
  border: 1px solid #ccdcd1;
  padding: 14px 22px;
  border-radius: 10px;
  font-size: 12px;
  background: #ffffff66;
}
.story-flow strong {
  background: #0f766e;
  color: white;
  border-color: #0f766e;
}
.story-flow i {
  color: #99b0a3;
}
.login-story footer {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #8ba193;
}
.login-form {
  min-width: 0;
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}
.login-form > div {
  width: min(360px, 100%);
  min-width: 0;
  max-width: 100%;
}
.login-footnote {
  font-size: 11px;
  color: #a2aaa5;
  text-align: center;
  margin-top: 32px;
}
@media (max-width: 767px) {
  .login-page {
    grid-template-columns: minmax(0, 1fr);
  }
  .login-story {
    padding: 20px 24px;
  }
  .login-story .brand {
    padding-bottom: 0;
  }
  .story-main,
  .login-story footer {
    display: none;
  }
  .login-form {
    padding: 40px 24px;
    align-items: start;
  }
}
</style>
