<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCredentialStore } from '@/stores/credential'
import { Message, type ValidatedError } from '@arco-design/web-vue'
import { provider } from '@/services/oauth'
import { passwordLogin } from '@/services/auth'

// 1.定义自定义组件所需数据
const errorMessage = ref('')
const passwordLoading = ref(false)
const githubLoading = ref(false)
const loginForm = reactive({ email: '', password: '' })
const credentialStore = useCredentialStore()
const router = useRouter()
const route = useRoute()
const destination = () => {
  const p = String(route.query.redirect || '/home')
  return p.startsWith('/') && !p.startsWith('//') ? p : '/home'
}

// 2.定义忘记密码点击事件
const forgetPassword = () => Message.error('忘记密码请联系管理员')

// 3.定义github第三方授权认证登录
const githubLogin = async () => {
  try {
    githubLoading.value = true
    const resp = await provider('github')
    sessionStorage.setItem('youyou-login-return', destination())
    window.location.href = resp.data.redirect_url
  } finally {
    githubLoading.value = false
  }
}

// 4.账号密码登录
const handleSubmit = async ({ errors }: { errors: Record<string, ValidatedError> | undefined }) => {
  // 4.1 判断表单是否校验成功
  if (errors) return

  // 4.2 如果没有出错则发起请求进行登录
  try {
    // 4.3 发起账号密码登录，并且将loading设置为true
    passwordLoading.value = true
    const resp = await passwordLogin(loginForm.email, loginForm.password)
    Message.success('登录成功，正在跳转')
    credentialStore.update(resp.data)
    await router.replace(destination())
  } catch (error: any) {
    // 4.4 添加错误信息并清除密码
    errorMessage.value = error.message
    loginForm.password = ''
  } finally {
    passwordLoading.value = false
  }
}
</script>

<template>
  <div class="">
    <!-- 顶部标题 -->
    <div class="text-gray-900 font-bold text-2xl leading-8">登录 Youyou LLMOPS</div>
    <p class="text-base leading-6 text-gray-600">欢迎回来，继续构建你的 AI 应用。</p>
    <!-- 错误提示占位符 -->
    <div class="h-8 text-red-700 leading-8 line-clamp-1">{{ errorMessage }}</div>
    <!-- 登录表单 -->
    <a-form
      :model="loginForm"
      @submit="handleSubmit"
      layout="vertical"
      size="large"
      class="flex flex-col w-full"
    >
      <a-form-item
        field="email"
        :rules="[{ type: 'email', required: true, message: '登录账号必须是合法的邮箱' }]"
        :validate-trigger="['change', 'blur']"
        label="邮箱"
      >
        <a-input
          v-model="loginForm.email"
          size="large"
          placeholder="登录账号"
          autocomplete="username"
        >
          <template #prefix>
            <icon-user />
          </template>
        </a-input>
      </a-form-item>
      <a-form-item
        field="password"
        :rules="[{ required: true, message: '账号密码不能为空' }]"
        :validate-trigger="['change', 'blur']"
        label="密码"
      >
        <a-input-password
          v-model="loginForm.password"
          size="large"
          placeholder="账号密码"
          autocomplete="current-password"
        >
          <template #prefix>
            <icon-lock />
          </template>
        </a-input-password>
      </a-form-item>
      <a-space :size="16" direction="vertical">
        <div class="flex justify-between">
          <span class="text-xs text-gray-400">安全登录到你的工作空间</span>
          <a-link @click="forgetPassword">忘记密码?</a-link>
        </div>
        <a-button :loading="passwordLoading" size="large" type="primary" html-type="submit" long>
          登录
        </a-button>
        <a-divider>第三方授权</a-divider>
        <a-button :loading="githubLoading" size="large" type="dashed" long @click="githubLogin">
          <template #icon>
            <icon-github />
          </template>
          Github
        </a-button>
      </a-space>
    </a-form>
  </div>
</template>

<style scoped></style>
