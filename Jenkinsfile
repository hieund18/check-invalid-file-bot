pipeline {
    agent any

    triggers {
        pollSCM('H/5 * * * *')   // check repo mỗi 5 phút
    }

    environment {
        // Sử dụng Jenkins Credentials để lưu trữ token một cách an toàn
        BOT_TOKEN = credentials('BOT_TOKEN')
        TELEGRAM_CHAT_ID = "-4960856865"
        
        // Các đường dẫn này sẽ là đường dẫn bên trong workspace của Jenkins
        // Jenkins sẽ tự động tạo một thư mục làm việc (workspace) cho mỗi job
        REPO_PATH = "${env.WORKSPACE}/outsource"
        DEST_PATH = "${env.WORKSPACE}/outsource_cleaned"
        JSON_PATH = "${env.WORKSPACE}/ProvinceRules.json"
        DEPLOY_REPO = "${env.WORKSPACE}/PM2_VNPTHISL2_DEPLOY"
        GIT_BRANCH = "UPCODE_VTT"
    }

    stages {
        stage('Setup Environment') {
            steps {
                script {
                    try {
                        sh """
                            scl enable rh-python38 '
                                echo "--- Inside SCL environment ---"
                                rm -rf venv
                                python -m venv venv
                                source venv/bin/activate
                                python -m pip install --upgrade pip
                                pip install -r requirements.txt
                                echo "--- Environment setup complete ---"
                            '
                        """
                    } catch (e) {
                        echo "Lỗi xảy ra trong stage Setup Environment!"
                        def errorMessage = "❌ **[LỖI MÔI TRƯỜDNG]** Job **'${env.JOB_NAME}'** build **#${env.BUILD_NUMBER}** đã thất bại khi cài đặt thư viện.\n\n**Chi tiết:**\n`${e.getMessage()}`"
                        
                        withCredentials([string(credentialsId: 'BOT_TOKEN', variable: 'TELEGRAM_TOKEN')]) {
                            sh """
                                curl -s -X POST -H 'Content-Type: application/json' \
                                     -d '{"chat_id": "${TELEGRAM_CHAT_ID}", "text": "${errorMessage}", "parse_mode": "Markdown"}' \
                                     "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage"
                            """
                        }
                        
                        error "Build failed in Setup Environment stage"
                    }
                }
            }
        }

        stage('Prepare Source Repo (REPO_PATH)') {
            steps {
                script{
                    try{
                        sh """
                            echo ">>> Đang chuẩn bị kho nguồn (REPO_PATH)..."
                            
                            SOURCE_REPO_URL="http://10.168.3.145:8887/outsource.git"
                            SOURCE_BRANCH="UPCODE_VTT"

                            if [ -d "${REPO_PATH}" ]; then
                                echo "Thư mục nguồn đã tồn tại. Đang cập nhật..."
                                cd "${REPO_PATH}"
                                git checkout "\${SOURCE_BRANCH}"
                                git pull
                            else
                                echo "Thư mục nguồn chưa tồn tại. Đang clone nhánh \${SOURCE_BRANCH}..."
                                git clone -b "\${SOURCE_BRANCH}" "\${SOURCE_REPO_URL}" "${REPO_PATH}"
                            fi
                            echo ">>> Kho nguồn đã sẵn sàng."
                        """
                    } catch (e) {
                        echo "Lỗi xảy ra trong stage Prepare Source Repo!"
                        def errorMessage = "❌ **[LỖI khi chuẩn bị source repo]** Job **'${env.JOB_NAME}'** build **#${env.BUILD_NUMBER}** đã thất bại khi cài đặt thư viện.\n\n**Chi tiết:**\n`${e.getMessage()}`"
                        
                        withCredentials([string(credentialsId: 'BOT_TOKEN', variable: 'TELEGRAM_TOKEN')]) {
                            sh """
                                curl -s -X POST -H 'Content-Type: application/json' \
                                     -d '{"chat_id": "${TELEGRAM_CHAT_ID}", "text": "${errorMessage}", "parse_mode": "Markdown"}' \
                                     "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage"
                            """
                        }
                        
                        error "Build failed in Setup Environment stage"
                    }
                }
                
            }
        }

        stage('Prepare Deploy Repo') {
            steps {
                sh """
                    echo ">>> Đang chuẩn bị kho deploy (DEPLOY_REPO)..."

                    DEPLOY_REPO_URL="https://scm.devops.vnpt.vn/scm.ehealth.it/PM2_VNPTHISL2_DEPLOY.git"

                    if [ -d "${DEPLOY_REPO}" ]; then
                      echo "Thư mục deploy đã tồn tại. Đang cập nhật..."
                      cd "${DEPLOY_REPO}"
                      git pull
                    else
                      echo "Thư mục deploy chưa tồn tại. Đang clone..."
                      git clone "\${DEPLOY_REPO_URL}" "${DEPLOY_REPO}"
                    fi

                    echo ">>> Kho deploy đã sẵn sàng."
                """
            }
        }

        stage('Run Telegram Bot') {
            steps {
                script {
                    echo "Stopping any previous running bot instance..."
                    // Tìm và dừng tiến trình bot cũ nếu có, để tránh chạy nhiều con bot cùng lúc
                    // Lệnh `|| true` để job không bị lỗi nếu không tìm thấy tiến trình nào
                    def SCRIPT_NAME = 'CheckInvalidFile.py' 

                    sh "pkill -f 'CheckInvalidFile.py' || true"
                    
                    echo "Starting the bot in the background..."
                    // Chạy bot trong nền (background) bằng `nohup` và `&`
                    // Log của bot sẽ được ghi vào file bot.log
                    sh "scl enable rh-python38 'nohup venv/bin/python CheckInvalidFile.py > bot.log 2>&1 &'"
                }
            }
        }
    }
    
    post {
        // Kịch bản này sẽ chạy NẾU pipeline THÀNH CÔNG
        success {
            script {
                echo "Pipeline thành công! Đang gửi thông báo..."
                
                // Sử dụng withCredentials để truy cập biến BOT_TOKEN một cách an toàn
                withCredentials([string(credentialsId: 'BOT_TOKEN', variable: 'TELEGRAM_TOKEN')]) {
                    // Tạo nội dung tin nhắn
                    def successMessage = "✅ **[THÀNH CÔNG]** Job **'${env.JOB_NAME}'** build **#${env.BUILD_NUMBER}** đã khởi động lại Bot thành công."
                    
                    sh """
                        curl -s -X POST -H 'Content-Type: application/json' \
                            -d '{"chat_id": "${TELEGRAM_CHAT_ID}", "text": "${successMessage}", "parse_mode": "Markdown"}' \
                            "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage"
                    """
                }
            }
        }
        
        // Kịch bản này sẽ chạy NẾU pipeline THẤT BẠI
        failure {
            script {
                echo "Pipeline thất bại! Đang gửi thông báo..."

                withCredentials([string(credentialsId: 'BOT_TOKEN', variable: 'TELEGRAM_TOKEN')]) {
                    // Tạo nội dung tin nhắn
                    def failureMessage = "❌ **[THẤT BẠI]** Job **'${env.JOB_NAME}'** build **#${env.BUILD_NUMBER}** đã gặp lỗi.\nXem chi tiết tại: ${env.BUILD_URL}"
                    
                    sh """
                        curl -s -X POST -H 'Content-Type: application/json' \
                            -d '{"chat_id": "${TELEGRAM_CHAT_ID}", "text": "${failureMessage}", "parse_mode": "Markdown"}' \
                            "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage"
                    """
                }
            }
        }
    }
}